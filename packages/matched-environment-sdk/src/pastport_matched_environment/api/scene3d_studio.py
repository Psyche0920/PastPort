"""Optional Marble attachment UI alongside the unchanged panorama generation flow."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import SecretStr
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from pastport_matched_environment.application.reference_environment import (
    read_json,
    record,
    sequence,
    string,
)
from pastport_matched_environment.application.reference_preview import ReferencePreviewPool
from pastport_matched_environment.application.storage import atomic_write
from pastport_matched_environment.application.studio import StudioJobs
from pastport_matched_environment.domain.scene3d import (
    Scene3DNavigation,
    Scene3DRecord,
    Scene3DTransition,
)


class Scene3DPortal:
    """A separate attachment job; no extra inference or implicit Marble generation."""

    def __init__(self, app: FastAPI, jobs: StudioJobs, previews: ReferencePreviewPool) -> None:
        self.jobs, self.previews = jobs, previews
        self.lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._active_run: str | None = None
        self._api_key: SecretStr | None = None

        def source(job_id: str) -> Path:
            selected = next((job for job in jobs.list() if job.job_id == job_id), None)
            if selected is None or selected.status not in ("completed", "completed_with_gaps"):
                raise HTTPException(404, "Choose a completed matched environment")
            from pastport_matched_environment.domain.environment import RunResultPointer

            workspace = jobs.root / "projects" / selected.project_id
            pointer = RunResultPointer.model_validate_json(
                (workspace / "runs" / job_id / "result-pointer.json").read_bytes()
            )
            return workspace / "runs" / pointer.result_run_id / "result"

        @app.get("/api/scene3d-key")
        def key_status() -> dict[str, bool]:
            return {
                "configured": self._api_key is not None or bool(os.environ.get("WORLDLABS_API_KEY"))
            }

        @app.post("/api/scene3d-key")
        async def set_key(request: Request) -> dict[str, bool]:
            payload = bytearray()
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > 2048:
                    raise HTTPException(422, "API Key input is too large")
            try:
                value = record(json.loads(payload))
                key = value.get("key")
                if not isinstance(key, str) or not 10 <= len(key.strip()) <= 512:
                    raise ValueError("Invalid key shape")
                if any(char.isspace() for char in key.strip()):
                    raise ValueError("Whitespace in key")
                self._api_key = SecretStr(key.strip())
            except (ValueError, TypeError):
                raise HTTPException(422, "请输入有效的 Marble API Key。密钥不会回显。") from None
            return {"configured": True}

        @app.delete("/api/scene3d-key")
        def clear_key() -> dict[str, bool]:
            self._api_key = None
            return {"configured": bool(os.environ.get("WORLDLABS_API_KEY"))}

        @app.get("/scene3d", response_class=HTMLResponse)
        def page() -> str:
            from importlib.resources import files

            return files("pastport_matched_environment").joinpath("web/scene3d.html").read_text()

        @app.get("/api/scene3d-context/{job_id}")
        def context(job_id: str) -> dict[str, str]:
            environment = source(job_id)
            html = (environment / "vr_trial/index.html").read_text()
            match = re.search(
                r'<script id="tour-data" type="application/json">(.*?)</script>', html, re.S
            )
            if match is None:
                raise HTTPException(422, "Source panorama unavailable")
            tour = record(json.loads(match.group(1)))
            selected = next(job for job in jobs.list() if job.job_id == job_id)
            return {"title": selected.title, "scene_id": string(tour["firstSceneId"])}

        @app.get("/api/scene3d-sources/{job_id}")
        def scenes(job_id: str) -> list[str]:
            environment = source(job_id)
            html = (environment / "vr_trial/index.html").read_text()
            match = re.search(
                r'<script id="tour-data" type="application/json">(.*?)</script>', html, re.S
            )
            if match is None:
                raise HTTPException(422, "Source panorama unavailable")
            tour = record(json.loads(match.group(1)))
            return [string(record(scene)["id"]) for scene in sequence(tour["scenes"])]

        @app.get("/api/scene3d-deliveries")
        def deliveries() -> list[Scene3DRecord]:
            parent = jobs.root / "scene3d"
            if not parent.exists():
                return []
            titles = {job.job_id: job.title for job in jobs.list()}
            records: list[Scene3DRecord] = []
            for root in sorted(
                parent.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True
            ):
                if not root.is_dir() or len(root.name) != 32:
                    continue
                generation = (root / "generation-options.json").is_file()
                metadata = root / (
                    "generation-options.json" if generation else "import-options.json"
                )
                options = record(read_json(metadata)) if metadata.is_file() else {}
                source_id = options.get("job_id", "")
                scene_id = str(options.get("scene_id", ""))
                try:
                    source_views = scenes(str(source_id))
                except (HTTPException, OSError, ValueError):
                    source_views = []
                number = source_views.index(scene_id) + 1 if scene_id in source_views else 0
                title = titles.get(str(source_id), "已有匹配场景") + (
                    f" · 点位 {number} · 3D" if number else " · 未知点位 · 3D"
                )
                base = f"/scene3d-results/{root.name}/"
                ready = (root / "job/delivery.json").is_file() or (
                    root / "job/attachment/delivery.json"
                ).is_file()
                status, message, resume_url = (
                    "recovery_required",
                    "任务未完成，原始资料与记录保留；未自动重试。",
                    "",
                )
                if ready:
                    status, message = (
                        "pending_manual_acceptance",
                        "3D 输出已保存，等待对齐、热点校准和人工验收。",
                    )
                elif (
                    self._active_run == root.name
                    and self._process is not None
                    and self._process.returncode is None
                ):
                    status, message = "running", "正在提交、查询或导入资产。"
                elif generation:
                    operation = root / "job/operation.json"
                    if operation.is_file():
                        saved = record(read_json(operation))
                        if saved.get("error"):
                            status, message = (
                                "recovery_required",
                                "Marble 任务失败；保留原任务，不重新生成。",
                            )
                        elif not saved.get("done"):
                            status, message = (
                                "generation_pending",
                                "Marble 处理中；点击查询原任务，不重复生成。",
                            )
                            resume_url = f"/api/scene3d-resume/{root.name}"
                    elif not (root / "job/dispatched.json").exists():
                        status, message = (
                            "not_submitted",
                            "尚未提交生成，请检查本机密钥及本次授权。",
                        )
                records.append(
                    Scene3DRecord(
                        run_id=root.name,
                        job_id=str(source_id),
                        source_title=titles.get(str(source_id), "已有匹配场景"),
                        source_scene_id=scene_id,
                        viewpoint_number=number,
                        viewpoint_count=len(source_views),
                        title=title,
                        mode="generate" if generation else "import",
                        status=status,
                        message=message,
                        url=base if ready else "",
                        review_url=base + "?target=review" if ready else "",
                        splat_url=base + "?target=spz" if ready else "",
                        collider_url=base + "?target=glb" if ready else "",
                        manifest_url=base + "?target=manifest" if ready else "",
                        package_url=base + "?target=package" if ready else "",
                        resume=resume_url,
                    )
                )
            return records

        @app.post("/api/scene3d-attach")
        async def attach(request: Request) -> dict[str, str]:
            if self.lock.locked() or jobs.busy:
                raise HTTPException(409, "Wait for the active generation/import to finish")
            async with self.lock:
                async with request.form(max_files=1, max_fields=2) as form:
                    job_id, scene_id, world = (
                        form.get("job_id"),
                        form.get("scene_id"),
                        form.get("world"),
                    )
                    if (
                        not isinstance(job_id, str)
                        or not isinstance(scene_id, str)
                        or not isinstance(world, UploadFile)
                    ):
                        raise HTTPException(
                            422, "Select a matched result, viewpoint and world.json"
                        )
                    environment = source(job_id)
                    raw = await world.read(2 * 1024**2 + 1)
                    if not 0 < len(raw) <= 2 * 1024**2:
                        raise HTTPException(422, "world.json exceeds 2 MiB")
                    run_id = uuid4().hex
                    root = jobs.root / "scene3d" / run_id
                    root.mkdir(parents=True)
                    (root / "import-options.json").write_text(
                        json.dumps({"job_id": job_id, "scene_id": scene_id})
                    )
                    path = root / "world.json"
                    path.write_bytes(raw)
                    try:
                        self._active_run = run_id
                        self._process = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "pastport_matched_environment.cli",
                            "scene3d-attach",
                            "--environment",
                            str(environment),
                            "--world",
                            str(path),
                            "--workspace",
                            str(root / "job"),
                            "--source-scene",
                            scene_id,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        try:
                            code = await self._process.wait()
                            if code != 0:
                                raise ValueError(
                                    "Attachment failed; inspect the retained stage journal"
                                )
                        finally:
                            await self.close()
                    except (OSError, ValueError, KeyError, RuntimeError) as error:
                        raise HTTPException(
                            422,
                            "3D import stopped; original result and usage retained."
                            " Check the export and import job.",
                        ) from error
                    return {
                        "url": f"/scene3d-results/{run_id}/",
                        "status": "pending_alignment_and_manual_acceptance",
                    }

        async def generate_job(run_id: str) -> dict[str, str]:
            if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
                raise HTTPException(404)
            root = jobs.root / "scene3d" / run_id
            options = record(read_json(root / "generation-options.json"))
            environment = source(string(options["job_id"]))
            if self.lock.locked() or jobs.busy:
                raise HTTPException(409, "Another task is active")
            async with self.lock:
                if self._api_key is None and not os.environ.get("WORLDLABS_API_KEY"):
                    raise HTTPException(422, "请先在页面设置 Marble API Key。尚未提交生成。")
                environment_variables = dict(os.environ)
                if self._api_key is not None:
                    environment_variables["WORLDLABS_API_KEY"] = self._api_key.get_secret_value()
                self._active_run = run_id
                self._process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pastport_matched_environment.cli",
                    "scene3d-generate",
                    "--environment",
                    str(environment),
                    "--workspace",
                    str(root / "job"),
                    "--source-scene",
                    string(options["scene_id"]),
                    "--model",
                    string(options["model"]),
                    "--credit-budget",
                    str(options["credit_budget"]),
                    "--authorize-marble",
                    env=environment_variables,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    if await self._process.wait() != 0:
                        raise HTTPException(
                            422,
                            "Marble task stopped. Check local "
                            "key, authorization and saved "
                            "operation; do not start a new job"
                            " to retry unknown usage.",
                        )
                finally:
                    await self.close()
            if (root / "job/attachment/delivery.json").is_file():
                return {"url": f"/scene3d-results/{run_id}/", "status": "pending_manual_acceptance"}
            return {"resume": f"/api/scene3d-resume/{run_id}", "status": "generation_pending"}

        @app.post("/api/scene3d-generate")
        async def generate(request: Request) -> dict[str, str]:
            async with request.form(max_files=0, max_fields=5) as form:
                job_id, scene_id, model, budget, authorize = (
                    form.get(k)
                    for k in ("job_id", "scene_id", "model", "credit_budget", "authorize")
                )
                if (
                    not isinstance(job_id, str)
                    or not isinstance(scene_id, str)
                    or model not in ("marble-1.1", "marble-1.0-draft")
                    or authorize != "yes"
                    or not isinstance(budget, str)
                    or not budget.isdigit()
                ):
                    raise HTTPException(422, "Explicit single-job Marble authorization required")
                source(job_id)
                expected = {
                    "job_id": job_id,
                    "scene_id": scene_id,
                    "model": model,
                    "credit_budget": int(budget),
                }
                # A reconnect, refresh or repeated POST must never create a second paid world.
                # Each source viewpoint owns one generation; changed authorization needs review.
                run_id = hashlib.sha256(f"{job_id}:{scene_id}".encode()).hexdigest()[:32]
                parent = jobs.root / "scene3d"
                for previous in parent.glob("*/generation-options.json"):
                    saved = record(read_json(previous))
                    if saved.get("job_id") == job_id and saved.get("scene_id") == scene_id:
                        run_id = previous.parent.name
                        break
                root = parent / run_id
                root.mkdir(parents=True, exist_ok=True)
                options_path = root / "generation-options.json"
                if options_path.exists():
                    if read_json(options_path) != expected:
                        raise HTTPException(
                            409, "此 VR 已有生成任务。请核对原任务，不可改参数重复扣费。"
                        )
                else:
                    options_path.write_text(json.dumps(expected))
            return await generate_job(run_id)

        @app.post("/api/scene3d-resume/{run_id}")
        async def resume(run_id: str) -> dict[str, str]:
            return await generate_job(run_id)

        def result_root(run_id: str) -> Path:
            if not re.fullmatch(r"[a-f0-9]{32}", run_id):
                raise HTTPException(404)
            for suffix in ("job/result", "job/attachment/result"):
                candidate = jobs.root / "scene3d" / run_id / suffix
                if (candidate / "scene3d/attachment.json").is_file():
                    return candidate
            raise HTTPException(404, "3D result unavailable")

        def navigation_payload(run_id: str, base_url: str) -> Scene3DNavigation:
            result_root(run_id)
            from pastport_matched_environment.application.navigation import NavigationStore

            parent = jobs.root / "scene3d" / run_id
            metadata = parent / "generation-options.json"
            if not metadata.is_file():
                metadata = parent / "import-options.json"
            options = record(read_json(metadata))
            job_id, scene_id = string(options["job_id"]), string(options["scene_id"])
            links = NavigationStore(source(job_id)).current()
            targets: dict[str, str] = {}
            for path in (jobs.root / "scene3d").iterdir():
                for filename in ("generation-options.json", "import-options.json"):
                    descriptor = path / filename
                    if not descriptor.is_file():
                        continue
                    other = record(read_json(descriptor))
                    if other.get("job_id") != job_id:
                        continue
                    try:
                        result_root(path.name)
                    except HTTPException:
                        continue
                    targets[string(other["scene_id"])] = path.name
            transitions = []
            for link in links:
                if link.scene_id != scene_id or link.target_id not in targets:
                    continue
                query = {}
                if link.arrival:
                    query = {"arrival_yaw": link.arrival.yaw, "arrival_pitch": link.arrival.pitch}
                url = base_url + "scene3d-results/" + targets[link.target_id] + "/"
                if query:
                    url += "?" + urlencode(query)
                transitions.append(
                    Scene3DTransition(
                        hotspot_id=link.hotspot_id,
                        target_scene_id=link.target_id,
                        yaw=link.position.yaw,
                        pitch=link.position.pitch,
                        target_url=url,
                    )
                )
            return Scene3DNavigation(source_scene_id=scene_id, transitions=tuple(transitions))

        @app.get("/api/scene3d-tour/{job_id}/package")
        def tour_package(job_id: str) -> FileResponse:
            from pastport_matched_environment.application.scene3d_tour import (
                TourSource,
                export_tour,
            )

            source_ids = scenes(job_id)
            ready: dict[str, Scene3DRecord] = {}
            for item in deliveries():
                if item.job_id == job_id and item.url:
                    ready.setdefault(item.source_scene_id, item)
            if not source_ids or any(scene not in ready for scene in source_ids):
                raise HTTPException(
                    409, "Generate every source viewpoint before downloading the tour"
                )
            from pastport_matched_environment.application.shared_content import (
                SharedContentAuthority,
            )

            try:
                for scene in source_ids:
                    SharedContentAuthority(result_root(ready[scene].run_id)).bind(source(job_id))
            except (ValueError, OSError, sqlite3.Error) as error:
                raise HTTPException(
                    409, "Shared review binding needs attention: " + str(error)
                ) from error
            views = tuple(
                TourSource(index + 1, scene, result_root(ready[scene].run_id))
                for index, scene in enumerate(source_ids)
            )
            temporary = TemporaryDirectory(prefix="pastport-tour-")
            archive = Path(temporary.name) / "pastport-3d-tour.zip"
            try:
                export_tour(views, archive)
            except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile) as error:
                temporary.cleanup()
                raise HTTPException(
                    422, "Tour export failed; existing scenes are unchanged"
                ) from error
            return FileResponse(
                archive,
                media_type="application/zip",
                filename="pastport-3d-tour.zip",
                background=BackgroundTask(temporary.cleanup),
            )

        @app.get("/api/scene3d-navigation/{run_id}")
        async def navigation(run_id: str, request: Request) -> JSONResponse:
            root = result_root(run_id)
            payload = navigation_payload(run_id, str(request.base_url))
            port = await previews.ensure(root)
            origin = request.headers.get("origin", "")
            allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            if origin and origin not in allowed:
                raise HTTPException(403, "Owned result preview required")
            return JSONResponse(
                payload.model_dump(),
                headers={
                    "Access-Control-Allow-Origin": origin
                    if origin
                    else str(request.base_url).rstrip("/"),
                    "Vary": "Origin",
                    "Cache-Control": "no-store",
                },
            )

        @app.get("/scene3d-results/{run_id}/")
        async def result(
            run_id: str,
            request: Request,
            arrival_yaw: Annotated[
                float | None, Query(ge=-180, le=180, allow_inf_nan=False)
            ] = None,
            arrival_pitch: Annotated[
                float | None, Query(ge=-90, le=90, allow_inf_nan=False)
            ] = None,
            target: Literal["viewer", "review", "spz", "glb", "manifest", "package"] = "viewer",
        ) -> RedirectResponse:
            if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
                raise HTTPException(404)
            root = jobs.root / "scene3d" / run_id / "job" / "result"
            if not (root / "scene3d/attachment.json").is_file():
                root = jobs.root / "scene3d" / run_id / "job/attachment/result"
            if not (root / "scene3d/attachment.json").is_file():
                raise HTTPException(404, "3D result unavailable")
            if request.url.hostname not in ("127.0.0.1", "localhost"):
                raise HTTPException(403, "Loopback Studio required")
            atomic_write(
                root / "scene3d/arrow-seed.json",
                navigation_payload(run_id, str(request.base_url)).model_dump_json(),
            )
            atomic_write(
                root / "scene3d/portal-navigation.json",
                json.dumps(
                    {"endpoint": str(request.base_url) + "api/scene3d-navigation/" + run_id}
                ),
            )
            from pastport_matched_environment.application.shared_content import (
                SharedContentAuthority,
            )

            parent = jobs.root / "scene3d" / run_id
            metadata = parent / "generation-options.json"
            if not metadata.is_file():
                metadata = parent / "import-options.json"
            options = record(read_json(metadata))
            try:
                SharedContentAuthority(root).bind(source(string(options["job_id"])))
            except (ValueError, OSError, sqlite3.Error) as error:
                raise HTTPException(
                    409, "Shared review binding needs attention: " + str(error)
                ) from error
            port = await previews.ensure(root)
            suffix = {
                "viewer": "scene3d/index.html",
                "review": "",
                "spz": "scene3d/scene.spz",
                "glb": "scene3d/collider.glb",
                "manifest": "scene3d/attachment.json",
                "package": "api/scene3d-export",
            }[target]
            if target == "viewer" and arrival_yaw is not None and arrival_pitch is not None:
                suffix += "?" + urlencode(
                    {"arrival_yaw": arrival_yaw, "arrival_pitch": arrival_pitch}
                )
            return RedirectResponse(f"http://127.0.0.1:{port}/{suffix}")

    async def close(self) -> None:
        process = self._process
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()
        self._process = None
        self._active_run = None
