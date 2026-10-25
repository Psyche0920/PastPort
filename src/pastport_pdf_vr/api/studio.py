"""Browser generation portal sharing the existing per-project review application."""

from __future__ import annotations

import asyncio
import fcntl
import json
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.api.server import LocalReviewApplication
from pastport_pdf_vr.application.inputs import InputValidationError
from pastport_pdf_vr.application.studio import (
    MIB,
    BuildRunner,
    StudioJobs,
    SubprocessBuildRunner,
    prepare_tour,
    safe_relative_name,
)
from pastport_pdf_vr.domain.build import BuildSummary
from pastport_pdf_vr.domain.studio import (
    INPUT_CAPABILITIES,
    InputCapability,
    StudioJob,
    StudioOptions,
)
from pastport_pdf_vr.domain.tour import ImportedTour


class UploadLimitExceeded(ValueError):
    pass


class UploadBoundary:
    """Count actual received bytes, including chunked requests, before multipart storage."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        total = 0

        async def bounded_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > 720 * MIB:
                    raise UploadLimitExceeded
            return message

        await self.app(scope, bounded_receive, send)


class ProjectReviewRouter:
    def __init__(self, jobs: StudioJobs) -> None:
        self.jobs = jobs

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope["path"])
        prefix = str(scope.get("root_path", ""))
        relative = path[len(prefix) :] if path.startswith(prefix) else path
        project, _, remainder = relative.lstrip("/").partition("/")
        known = [j for j in self.jobs.list() if j.project_id == project]
        if not known or known[0].status not in ("completed", "completed_with_gaps"):
            await JSONResponse({"detail": "项目尚未完成，请返回生成工作台。"}, status_code=409)(
                scope, receive, send
            )
            return
        workspace = self.jobs.root / "projects" / project
        tour = (
            ImportedTour.model_validate_json((workspace / "tour.json").read_bytes())
            if known[0].workflow == "vr_build"
            else None
        )
        summary = BuildSummary.model_validate_json((workspace / "build-summary.json").read_bytes())
        application = LocalReviewApplication(
            project,
            tour,
            SQLiteEditorialRepository(workspace / "editorial.sqlite3"),
            LocalAssetStore(workspace / "assets"),
            summary,
            mapping_pdf=workspace / "mapping.pdf" if known[0].workflow == "photo_mapping" else None,
            mapping_data=workspace / "mapping.json"
            if known[0].workflow == "photo_mapping"
            else None,
        )
        child = dict(scope)
        child["root_path"] = prefix + "/" + project
        # Preserve the full path: Starlette subtracts root_path during routing.
        if not remainder and not path.endswith("/"):
            child["path"] = path + "/"
        await application.app(child, receive, send)


class StudioApplication:
    def __init__(self, root: Path, runner: BuildRunner | None = None) -> None:
        self.jobs = StudioJobs(root, runner or SubprocessBuildRunner())
        web = Path(str(files("pastport_pdf_vr").joinpath("web")))

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            # A second studio must not mark another server's active job interrupted.
            with (self.jobs.root / "studio.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    self.jobs.recover_interrupted()
                    yield
                finally:
                    await self.jobs.close()
                    fcntl.flock(lock, fcntl.LOCK_UN)

        app = FastAPI(
            title="PastPort Studio",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
            lifespan=lifespan,
        )
        self.app = app
        app.add_middleware(UploadBoundary)
        app.mount("/static", StaticFiles(directory=web), name="static")

        @app.middleware("http")
        async def boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
            if request.url.hostname not in ("127.0.0.1", "localhost", "testserver"):
                return JSONResponse({"detail": "Local studio only"}, status_code=403)
            if request.method not in ("GET", "HEAD"):
                origin = request.headers.get("origin")
                if (
                    origin and origin != f"{request.url.scheme}://{request.url.netloc}"
                ) or request.headers.get("x-pastport-edit") != "1":
                    return JSONResponse({"detail": "Invalid local edit request"}, status_code=403)
            response = await call_next(request)
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "same-origin",
                    "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                    "connect-src 'self'; object-src 'none'; "
                    "frame-ancestors 'none'; base-uri 'none'",
                }
            )
            return response

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web / "studio.html")

        @app.get("/api/capabilities")
        def capabilities() -> tuple[InputCapability, ...]:
            return INPUT_CAPABILITIES

        @app.get("/api/jobs")
        def jobs() -> tuple[StudioJob, ...]:
            return tuple(
                j.model_copy(update={"stages": self.jobs.stages(j)}) for j in self.jobs.list()
            )

        @app.post("/api/jobs", status_code=202)
        async def submit(request: Request) -> StudioJob:
            if self.jobs.busy or self.jobs.submission_lock.locked():
                raise HTTPException(409, "已有上传或生成任务正在运行，请等待结束。")
            if shutil.which("pdftoppm") is None:
                raise HTTPException(503, "未安装 Poppler，生成服务尚未就绪。请让维护者安装后重试。")
            async with self.jobs.submission_lock:
                upload = self.jobs.root / "jobs" / uuid4().hex
                upload.mkdir()
                try:
                    async with request.form(
                        max_files=201, max_fields=1, max_part_size=16 * 1024
                    ) as form:
                        raw_options = form.get("options")
                        if not isinstance(raw_options, str):
                            raise InputValidationError("缺少生成设置。")
                        options = StudioOptions.model_validate_json(raw_options)
                        if options.document_format != "pdf" or options.scene_format != "tour_360":
                            raise InputValidationError(
                                "所选格式尚未接入，请使用 PDF 和 360° 导览。"
                            )
                        pdfs = form.getlist("document")
                        tours = form.getlist("tour")
                        photos = form.getlist("photos")
                        if (
                            len(pdfs) != 1
                            or (options.workflow == "vr_build" and not tours)
                            or (options.workflow == "photo_mapping" and not photos)
                        ):
                            raise InputValidationError("请选择一份 PDF 和完整的 VR 导览。")
                        if any(
                            key not in ("document", "tour", "photos", "options") for key in form
                        ):
                            raise InputValidationError("包含无法识别的上传字段。")
                        pdf_file = pdfs[0]
                        if (
                            not isinstance(pdf_file, UploadFile)
                            or Path(pdf_file.filename or "").suffix.lower() != ".pdf"
                        ):
                            raise InputValidationError("当前只支持 PDF；IDML/INDD 尚不能直接生成。")
                        pdf_path = upload / "source.pdf"
                        await self._save_upload(
                            pdf_file, pdf_path, (512 if options.large_pdf else 64) * MIB
                        )
                        if options.workflow == "photo_mapping":
                            if (
                                tours
                                or len(photos) > 100
                                or options.mapping_mode != "demo_substitution"
                            ):
                                raise InputValidationError(
                                    "照片映射只接受历史 PDF 与最多 100 张现场照片，"
                                    "请选择替代物模式。"
                                )
                            photo_folder = upload / "photos"
                            photo_folder.mkdir()
                            photo_names: set[str] = set()
                            total = 0
                            for item in photos:
                                if not isinstance(item, UploadFile):
                                    raise InputValidationError("照片必须为文件。")
                                relative = safe_relative_name(item.filename or "")
                                canonical = relative.as_posix().casefold()
                                if canonical in photo_names or relative.suffix.lower() not in (
                                    ".jpg",
                                    ".jpeg",
                                    ".png",
                                    ".webp",
                                ):
                                    raise InputValidationError(
                                        "照片格式或文件名重复；支持 JPEG、PNG、WebP。"
                                    )
                                photo_names.add(canonical)
                                target = photo_folder / relative
                                target.parent.mkdir(parents=True, exist_ok=True)
                                total += await self._save_upload(
                                    item, target, min(30 * MIB, 200 * MIB - total)
                                )
                            return self.jobs.start(options, upload, pdf_path, photo_folder)
                        if photos:
                            raise InputValidationError("请先选择照片映射阶段，以接收现场照片。")
                        tour_folder = upload / "tour"
                        tour_folder.mkdir()
                        names: set[str] = set()
                        total = 0
                        for item in tours:
                            if not isinstance(item, UploadFile):
                                raise InputValidationError("导览必须为文件。")
                            relative = safe_relative_name(item.filename or "")
                            canonical = relative.as_posix().casefold()
                            if canonical in names:
                                raise InputValidationError("导览包含重复路径。")
                            names.add(canonical)
                            target = tour_folder / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            total += await self._save_upload(item, target, 200 * MIB - total)
                        tour_path = await asyncio.to_thread(prepare_tour, tour_folder)
                        return self.jobs.start(options, upload, pdf_path, tour_path)
                except (InputValidationError, ValidationError, json.JSONDecodeError) as error:
                    self.jobs.discard_upload(upload)
                    detail = (
                        str(error)
                        if isinstance(error, InputValidationError)
                        else "生成设置不合法。"
                    )
                    raise HTTPException(422, detail) from error
                except UploadLimitExceeded as error:
                    self.jobs.discard_upload(upload)
                    raise HTTPException(413, "上传超过总大小限制 720 MiB。") from error
                except OSError as error:
                    self.jobs.discard_upload(upload)
                    raise HTTPException(503, "无法保存上传文件，请检查可用磁盘空间。") from error
                finally:
                    self.jobs.discard_upload(upload)

        app.mount("/projects", ProjectReviewRouter(self.jobs))

    @staticmethod
    async def _save_upload(source: UploadFile, path: Path, maximum: int) -> int:
        size = 0
        with path.open("xb") as output:
            while chunk := await source.read(MIB):
                size += len(chunk)
                if size > maximum:
                    raise InputValidationError("文件超过大小限制，请检查所选文件或大 PDF 选项。")
                output.write(chunk)
        if size == 0:
            raise InputValidationError("不能上传空文件。")
        return size
