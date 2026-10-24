"""Local generation jobs; subprocess ownership is separate from editorial state."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import sqlite3
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from pastport_pdf_vr.application.bootstrap import atomic_write
from pastport_pdf_vr.application.inputs import InputValidationError
from pastport_pdf_vr.domain.build import BuildSummary
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.studio import StudioJob, StudioOptions

logger = logging.getLogger(__name__)
MIB = 1024 * 1024


def safe_relative_name(name: str) -> Path:
    """Use browser paths only as contained relative asset names, never host paths."""
    parts = PurePosixPath(name)
    if (
        not name
        or len(name) > 512
        or parts.is_absolute()
        or "\\" in name
        or any(part in ("", ".", "..") for part in name.split("/"))
        or any(":" in part or "\x00" in part for part in parts.parts)
    ):
        raise InputValidationError("文件路径不安全，请重新打包导览文件。")
    return Path(*parts.parts)


def prepare_tour(folder: Path) -> Path:
    """Extract bounded ZIPs into a fresh directory without executing uploaded code."""
    paths = [p for p in folder.rglob("*") if p.is_file()]
    archives = [p for p in paths if p.suffix.lower() == ".zip"]
    if archives:
        if len(paths) != 1 or len(archives) != 1:
            raise InputValidationError("ZIP 导览请单独上传，不要同时选择其他导览文件。")
        archive_path = archives[0]
        if archive_path.stat().st_size > 150 * MIB:
            raise InputValidationError("导览 ZIP 超过 150 MiB。")
        destination = folder / "_extracted"
        destination.mkdir()
        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                if len(members) > 1000:
                    raise InputValidationError("导览 ZIP 成员数量超过 1000。")
                total = 0
                names: set[str] = set()
                for member in members:
                    name = member.filename.rstrip("/")
                    relative = safe_relative_name(name)
                    canonical = relative.as_posix().casefold()
                    if canonical in names:
                        raise InputValidationError("导览 ZIP 含重复文件路径。")
                    names.add(canonical)
                    mode = stat.S_IFMT(member.external_attr >> 16)
                    if mode not in (0, stat.S_IFDIR, stat.S_IFREG) or member.flag_bits & 1:
                        raise InputValidationError("导览 ZIP 不能包含链接、特殊文件或加密文件。")
                    if member.is_dir():
                        continue
                    total += member.file_size
                    if total > 200 * MIB:
                        raise InputValidationError("导览解压后超过 200 MiB。")
                    if "__MACOSX" in relative.parts or relative.name == ".DS_Store":
                        continue
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    actual = 0
                    with archive.open(member) as source, target.open("xb") as output:
                        while chunk := source.read(MIB):
                            actual += len(chunk)
                            if actual > member.file_size or actual > 200 * MIB:
                                raise InputValidationError("导览 ZIP 解压大小不符合声明。")
                            output.write(chunk)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as error:
            raise InputValidationError("无法读取导览 ZIP，请重新导出。") from error
        folder = destination
    entries = [p for p in folder.rglob("*") if p.name.lower() in ("index.html", "tour.html")]
    if not entries:
        html = [p for p in folder.rglob("*.html") if p.is_file()]
        if len(html) == 1:
            entries = html
    if len(entries) != 1 or not entries[0].is_file():
        raise InputValidationError(
            "请选择包含唯一 index.html 的完整导览；也可上传单个自包含 HTML。"
        )
    return entries[0]


class BuildRunner(Protocol):
    async def run(
        self,
        pdf: Path,
        tour: Path,
        grant: Path,
        workspace: Path,
        job_id: str,
        options: StudioOptions,
    ) -> int: ...
    async def close(self) -> None: ...


class SubprocessBuildRunner:
    """One owned process group, interrupted on shutdown without automatic redispatch."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None

    async def run(
        self,
        pdf: Path,
        tour: Path,
        grant: Path,
        workspace: Path,
        job_id: str,
        options: StudioOptions,
    ) -> int:
        arguments = [
            sys.executable,
            "-m",
            "pastport_pdf_vr.cli",
            "build",
            "--pdf",
            str(pdf),
            "--tour",
            str(tour),
            "--grant",
            str(grant),
            "--workspace",
            str(workspace),
            "--run-id",
            job_id,
            "--mapping-mode",
            options.mapping_mode,
        ]
        if options.large_pdf:
            arguments.append("--large-pdf")
        self._process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            return await self._process.wait()
        finally:
            await self.close()

    async def close(self) -> None:
        process = self._process
        if process is not None:
            # The SDK may own descendants even after its parent exits.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except TimeoutError:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()
            self._process = None


class StudioJobs:
    """Persist job metadata and bound one active build, keeping edits in project workspaces."""

    def __init__(self, root: Path, runner: BuildRunner) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "jobs").mkdir(exist_ok=True)
        (self.root / "projects").mkdir(exist_ok=True)
        self.runner = runner
        self.submission_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def recover_interrupted(self) -> None:
        for job in self.list():
            if job.status == "running":
                self.save(
                    job.model_copy(
                        update={
                            "status": "recovery_required",
                            "message": "上次运行被中断，未自动重试。请核对执行记录后再继续。",
                        }
                    )
                )

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def save(self, job: StudioJob) -> None:
        folder = self.root / "jobs" / job.job_id
        folder.mkdir(exist_ok=True)
        atomic_write(folder / "job.json", job.model_dump_json())

    def list(self) -> tuple[StudioJob, ...]:
        return tuple(
            StudioJob.model_validate_json(p.read_bytes())
            for p in sorted(
                (self.root / "jobs").glob("*/job.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        )

    def start(self, options: StudioOptions, upload: Path, pdf: Path, tour: Path) -> StudioJob:
        if options.document_format != "pdf" or options.scene_format != "tour_360":
            raise InputValidationError("所选资料或场景格式尚未接入，请使用 PDF 和 360° 导览。")
        if self.busy:
            raise InputValidationError("已有生成任务正在运行，请等待结束。")
        project = options.project_id or uuid4().hex
        previous = [j for j in self.list() if j.project_id == project]
        if options.project_id and not previous:
            raise InputValidationError("项目不存在。")
        if any(j.status == "recovery_required" for j in previous):
            raise InputValidationError("此项目有未核对的中断记录，不能重新提交模型任务。")
        job_id = upload.name
        workspace = self.root / "projects" / project
        if pdf.stat().st_size > (512 if options.large_pdf else 64) * MIB:
            raise InputValidationError("PDF 超过大小限制。")
        with pdf.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise InputValidationError("文件内容不是 PDF。")
        grant = SubscriptionGrant(
            grant_ref="studio:" + job_id,
            project_id=project,
            max_calls=options.max_calls,
            max_recorded_tokens=options.max_recorded_tokens,
            timeout_seconds=180,
        )
        grant_path = upload / "grant.json"
        atomic_write(grant_path, grant.model_dump_json())
        job = StudioJob(job_id=job_id, project_id=project, title=options.title, status="running")
        self.save(job)
        self._task = asyncio.create_task(
            self._execute(job, options, pdf, tour, grant_path, workspace)
        )
        return job

    async def _execute(
        self,
        job: StudioJob,
        options: StudioOptions,
        pdf: Path,
        tour: Path,
        grant: Path,
        workspace: Path,
    ) -> None:
        try:
            code = await self.runner.run(pdf, tour, grant, workspace, job.job_id, options)
            summary_path = workspace / "build-summary.json"
            if code == 0 and summary_path.exists():
                summary = BuildSummary.model_validate_json(summary_path.read_bytes())
                self.save(
                    job.model_copy(
                        update={
                            "status": summary.status,
                            "message": "生成完成，可打开 VR 和审核工作台。",
                        }
                    )
                )
            else:
                # Do not reset usage or automatically retry unknown dispatches.
                self.save(
                    job.model_copy(
                        update={
                            "status": "recovery_required",
                            "message": "生成未完成。请检查登录、Poppler 和执行记录；不会自动重试。",
                        }
                    )
                )
        except asyncio.CancelledError:
            self.save(
                job.model_copy(
                    update={
                        "status": "recovery_required",
                        "message": "运行已中断，需核对执行记录。",
                    }
                )
            )
            raise
        except (OSError, ValueError, sqlite3.Error) as error:
            logger.error("Studio build failed: %s", type(error).__name__)
            self.save(
                job.model_copy(
                    update={
                        "status": "recovery_required",
                        "message": "生成服务发生错误，任务已停止；未自动重试。",
                    }
                )
            )

    def stages(self, job: StudioJob) -> tuple[str, ...]:
        path = self.root / "projects" / job.project_id / "stages.sqlite3"
        if not path.exists():
            return ()
        try:
            connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=1)
            try:
                return tuple(
                    f"{row[0]}:{row[1]}"
                    for row in connection.execute(
                        "SELECT stage,status FROM pipeline_stages WHERE project=? AND run_id=? "
                        "ORDER BY rowid",
                        (job.project_id, job.job_id),
                    )
                )
            finally:
                connection.close()
        except sqlite3.Error:
            return ()

    async def close(self) -> None:
        await self.runner.close()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def discard_upload(self, upload: Path) -> None:
        """Only remove a just-created, rejected upload, never a registered project."""
        if (
            upload.exists()
            and upload.parent == self.root / "jobs"
            and not (upload / "job.json").exists()
        ):
            shutil.rmtree(upload)
