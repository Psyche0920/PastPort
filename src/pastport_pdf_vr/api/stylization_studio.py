"""Upload, estimate and explicitly start supported VR/3D stylization jobs."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import re
import select
import subprocess
import sys
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import Literal
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from pastport_pdf_vr.application.animation_style import approved_animation_style
from pastport_pdf_vr.application.automatic_stylization import (
    AutomaticStyleDelivery,
    AutomaticStyleRun,
    StyleInput,
    inspect_input,
)
from pastport_pdf_vr.application.reference_preview import ReferencePreviewPool
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.application.stylization_agent import agent_call_limits
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.models import DomainModel


class StyleJob(DomainModel):
    run_id: str
    title: str
    upload_sha256: str
    source: StyleInput
    status: Literal["prepared", "running", "completed", "recovery_required"] = "prepared"
    message: str = "Fresh task ready. Starting creates new output; generation has not started."
    expected_tokens_low: int
    expected_tokens_high: int
    suggested_token_threshold: int
    authorized_calls: int | None = None
    authorized_tokens: int | None = None
    execution: Literal["pipeline", "agent"] = "pipeline"
    normal_model_calls: int = 0
    maximum_model_calls: int = 0
    style_profile: str = "legacy"
    upload_names: tuple[str, ...] = Field(default=(), max_length=10)
    upload_reused: bool = False


class StartStyle(DomainModel):
    authorize: Literal[True]
    max_calls: int | None = Field(default=None, ge=1, le=100)
    max_recorded_tokens: int | None = Field(default=None, ge=1, le=10_000_000)


class StylizationPortal:
    def __init__(self, app: FastAPI, workspace: Path, previews: ReferencePreviewPool) -> None:
        self.root = workspace.resolve() / "stylization"
        self.root.mkdir(parents=True, exist_ok=True)
        self.previews = previews
        self.process: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()
        self.upload_lock = asyncio.Lock()
        self.tour_previews: dict[str, tuple[subprocess.Popen[bytes], str]] = {}
        web = files("pastport_pdf_vr").joinpath("web")

        @app.get("/stylization")
        def page() -> FileResponse:
            return FileResponse(Path(str(web.joinpath("stylization.html"))))

        @app.get("/stylization.js")
        def script() -> FileResponse:
            return FileResponse(
                Path(str(web.joinpath("stylization.js"))), media_type="text/javascript"
            )

        @app.get("/api/stylization/jobs")
        def jobs() -> list[StyleJob]:
            return [
                StyleJob.model_validate_json(p.read_bytes())
                for p in sorted(
                    self.root.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True
                )
            ]

        @app.post("/api/stylization/uploads")
        async def upload(request: Request) -> StyleJob:
            async with self.upload_lock:
                async with request.form(
                    max_files=1, max_fields=4, max_part_size=2 * 1024**3
                ) as form:
                    item = form.get("package")
                    if not isinstance(item, UploadFile) or not (
                        item.filename or ""
                    ).lower().endswith(".zip"):
                        raise HTTPException(422, "Choose one complete VR or 3D tour ZIP.")
                    run_id = uuid4().hex
                    folder = self.root / run_id
                    folder.mkdir()
                    checksum = hashlib.sha256()
                    count = 0
                    with (folder / "upload.zip").open("xb") as stream:
                        while chunk := await item.read(1024**2):
                            count += len(chunk)
                            if count > 2 * 1024**3:
                                raise HTTPException(
                                    413, "Upload exceeds 2 GiB; retained, not executed."
                                )
                            checksum.update(chunk)
                            stream.write(chunk)
                    standard = approved_animation_style().standard
                    if standard is None:
                        raise HTTPException(503, "Approved style is unavailable")
                    try:
                        source = await asyncio.to_thread(
                            inspect_input, folder / "upload.zip", folder
                        )
                        if source.required_calls > 100:
                            raise ValueError(
                                "More than 16 viewpoints need a separately bounded batch."
                            )
                    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
                        raise HTTPException(422, str(error)) from error
                    try:
                        normal_calls, maximum_calls = agent_call_limits(source.viewpoints)
                    except ValueError as error:
                        raise HTTPException(422, str(error)) from error
                    review_calls = maximum_calls - source.required_calls * 2
                    job = StyleJob(
                        run_id=run_id,
                        title=(item.filename or "Tour")[:100],
                        upload_names=((item.filename or "Tour")[:100],),
                        upload_sha256=checksum.hexdigest(),
                        source=source,
                        expected_tokens_low=source.required_calls * 2 * 56068
                        + review_calls * 25000,
                        expected_tokens_high=source.required_calls * 2 * 85000
                        + review_calls * 50000,
                        suggested_token_threshold=source.required_calls * 2 * 100000
                        + review_calls * 50000,
                        execution="agent",
                        style_profile=standard.profile_id,
                        normal_model_calls=normal_calls,
                        maximum_model_calls=maximum_calls,
                    )
                    self.save(job)
                    return job

        @app.post("/api/stylization/{run_id}/start")
        async def start(run_id: str, request: Request) -> StyleJob:
            payload = bytearray()
            async for chunk in request.stream():
                payload.extend(chunk)
                if len(payload) > 4096:
                    raise HTTPException(413, "Generation options exceed the profile")
            try:
                options = StartStyle.model_validate_json(payload)
            except ValidationError as error:
                raise HTTPException(422, "Invalid generation options") from error
            async with self.lock:
                job = self.load(run_id)
                if job.status == "completed":
                    return job
                if self.task is not None and not self.task.done():
                    raise HTTPException(409, "One authorized job is already running.")
                folder = self.folder(run_id)
                request_path = folder / "run.json"
                if request_path.is_file():
                    original = AutomaticStyleRun.model_validate_json(request_path.read_bytes())
                    if (
                        options.max_calls is not None
                        and options.max_calls != original.grant.max_calls
                    ) or (
                        options.max_recorded_tokens is not None
                        and options.max_recorded_tokens != original.grant.max_recorded_tokens
                    ):
                        raise HTTPException(
                            409, "Resume must retain the original authorized budget."
                        )
                    command = original.model_copy(update={"resume": True})
                else:
                    required = (
                        job.maximum_model_calls
                        if job.execution == "agent"
                        else job.source.required_calls
                    )
                    calls = options.max_calls or required
                    if calls < required:
                        raise HTTPException(
                            422,
                            "Call limit cannot cover the run and one-repair reserve; not started.",
                        )
                    tokens = options.max_recorded_tokens or job.suggested_token_threshold
                    if tokens < job.expected_tokens_low:
                        raise HTTPException(
                            422,
                            "Token threshold is below the complete-tour estimate; not started.",
                        )
                    grant = SubscriptionGrant(
                        grant_ref="style-" + run_id,
                        project_id="style-" + run_id,
                        max_calls=calls,
                        max_recorded_tokens=tokens,
                        timeout_seconds=240,
                    )
                    command = AutomaticStyleRun(
                        source=job.source, workspace=str(folder / "output"), grant=grant
                    )
                atomic_write(request_path, command.model_dump_json())
                job = job.model_copy(
                    update={
                        "status": "running",
                        "authorized_calls": command.grant.max_calls,
                        "authorized_tokens": command.grant.max_recorded_tokens,
                        "message": "Generation started. Budget increases are disabled.",
                    }
                )
                self.save(job)
                self.task = asyncio.create_task(self.execute(job, request_path))
                return job

        @app.get("/api/stylization/{run_id}/download")
        def download(run_id: str) -> FileResponse:
            delivery = self.delivery(run_id)
            return FileResponse(
                delivery.archive, media_type="application/zip", filename="stylized-tour.zip"
            )

        @app.get("/api/stylization/{run_id}/review")
        def review(run_id: str) -> FileResponse:
            delivery = self.delivery(run_id)
            if delivery.agent_report is None:
                raise HTTPException(404, "This legacy result has no agent review")
            expected = self.folder(run_id) / "output/agent-report.json"
            if Path(delivery.agent_report).resolve() != expected.resolve():
                raise HTTPException(409, "Agent report binding differs")
            return FileResponse(expected, media_type="application/json")

        @app.get("/stylization-results/{run_id}/")
        async def view(run_id: str) -> RedirectResponse:
            delivery = self.delivery(run_id)
            if delivery.kind == "panorama":
                if delivery.environment is None:
                    raise HTTPException(409, "Missing output environment")
                port = await previews.ensure(Path(delivery.environment))
                return RedirectResponse(f"http://127.0.0.1:{port}/vr_trial/index.html")
            if run_id not in self.tour_previews:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "pastport_pdf_vr.application.stylization3d_preview",
                        "--delivery",
                        str(delivery.tour_delivery),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                if process.stdout is None or not await asyncio.to_thread(
                    lambda: bool(select.select([process.stdout], [], [], 20)[0])
                ):
                    process.terminate()
                    raise HTTPException(503, "Isolated preview did not start")
                url = json.loads(process.stdout.readline())["url"]
                self.tour_previews[run_id] = (process, str(url))
            return RedirectResponse(self.tour_previews[run_id][1])

    def recover(self) -> None:
        for path in self.root.glob("*/job.json"):
            saved = StyleJob.model_validate_json(path.read_bytes())
            if saved.status == "running":
                self.save(
                    saved.model_copy(
                        update={
                            "status": "recovery_required",
                            "message": "Server stopped. Resume the saved job; no automatic retry.",
                        }
                    )
                )

    def folder(self, run_id: str) -> Path:
        if re.fullmatch("[a-f0-9]{32}", run_id) is None:
            raise HTTPException(404, "Unknown stylization job")
        return self.root / run_id

    def save(self, job: StyleJob) -> None:
        atomic_write(self.folder(job.run_id) / "job.json", job.model_dump_json(indent=2))

    def load(self, run_id: str) -> StyleJob:
        try:
            return StyleJob.model_validate_json((self.folder(run_id) / "job.json").read_bytes())
        except FileNotFoundError as error:
            raise HTTPException(404, "Unknown stylization job") from error

    def delivery(self, run_id: str) -> AutomaticStyleDelivery:
        if self.load(run_id).status != "completed":
            raise HTTPException(409, "The complete result is not ready")
        return AutomaticStyleDelivery.model_validate_json(
            (self.folder(run_id) / "automatic-delivery.json").read_bytes()
        )

    async def execute(self, job: StyleJob, request_path: Path) -> None:
        try:
            folder = self.folder(job.run_id)
            with (folder / "worker.log").open("ab") as log:
                self.process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    (
                        "pastport_pdf_vr.application.stylization_agent_cli"
                        if job.execution == "agent"
                        else "pastport_pdf_vr.application.automatic_stylization"
                    ),
                    "--request",
                    str(request_path),
                    stdout=log,
                    stderr=log,
                )
                code = await self.process.wait()
            if code == 0 and (folder / "automatic-delivery.json").is_file():
                delivery = AutomaticStyleDelivery.model_validate_json(
                    (folder / "automatic-delivery.json").read_bytes()
                )
                message = (
                    "Agent finished; severe findings remain for your review."
                    if delivery.model_review == "needs_human_review"
                    else "Candidate saved; image review complete, final acceptance is yours."
                    if delivery.model_review
                    else "Candidate saved; visual and interaction review is yours."
                )
                self.save(
                    job.model_copy(
                        update={
                            "status": "completed",
                            "message": message,
                        }
                    )
                )
            else:
                self.save(
                    job.model_copy(
                        update={
                            "status": "recovery_required",
                            "message": "Stopped; saved inputs and usage retained. No retry.",
                        }
                    )
                )
        except OSError:
            self.save(
                job.model_copy(
                    update={
                        "status": "recovery_required",
                        "message": "Worker could not start. No automatic retry.",
                    }
                )
            )
        finally:
            self.process = None

    async def close(self) -> None:
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 10)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.task is not None:
            await self.task
        for process, _ in self.tour_previews.values():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()


def create_app(workspace: Path) -> FastAPI:
    from pastport_pdf_vr.api.studio import UploadBoundary

    previews = ReferencePreviewPool()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with (portal.root / "studio.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            portal.recover()
            try:
                yield
            finally:
                await portal.close()
                await previews.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    app = FastAPI(
        title="Environment stylization",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(UploadBoundary)
    app.mount("/static", StaticFiles(directory=str(files("pastport_pdf_vr").joinpath("web"))))
    portal = StylizationPortal(app, workspace, previews)

    @app.middleware("http")
    async def local_only(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.hostname not in ("localhost", "127.0.0.1", "testserver"):
            return JSONResponse({"detail": "Local application only"}, status_code=403)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if (
                origin and origin != f"{request.url.scheme}://{request.url.netloc}"
            ) or request.headers.get("x-pastport-edit") != "1":
                return JSONResponse({"detail": "Invalid local edit request"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def home() -> RedirectResponse:
        return RedirectResponse("/stylization")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8795)
    args = parser.parse_args()
    uvicorn.run(create_app(args.workspace), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
