"""Optional Marble attachment UI alongside the unchanged panorama generation flow."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.datastructures import UploadFile

from pastport_pdf_vr.application.reference_environment import read_json, record, sequence, string
from pastport_pdf_vr.application.reference_preview import ReferencePreviewPool
from pastport_pdf_vr.application.studio import StudioJobs


class Scene3DPortal:
    """A separate attachment job; no extra inference or implicit Marble generation."""

    def __init__(self, app: FastAPI, jobs: StudioJobs, previews: ReferencePreviewPool) -> None:
        self.jobs, self.previews = jobs, previews
        self.lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None

        def source(job_id: str) -> Path:
            selected = next((job for job in jobs.list() if job.job_id == job_id), None)
            if selected is None or selected.status not in ("completed", "completed_with_gaps"):
                raise HTTPException(404, "Choose a completed matched environment")
            from pastport_pdf_vr.domain.environment import RunResultPointer

            workspace = jobs.root / "projects" / selected.project_id
            pointer = RunResultPointer.model_validate_json(
                (workspace / "runs" / job_id / "result-pointer.json").read_bytes()
            )
            return workspace / "runs" / pointer.result_run_id / "result"

        @app.get("/scene3d", response_class=HTMLResponse)
        def page() -> str:
            from importlib.resources import files

            return files("pastport_pdf_vr").joinpath("web/scene3d.html").read_text()

        @app.get("/api/scene3d-sources/{job_id}")
        def scenes(job_id: str) -> list[str]:
            report = record(read_json(source(job_id) / "vr_trial/trial_report.json"))
            return sorted({string(record(row)["scene_id"]) for row in sequence(report["located"])})

        @app.get("/api/scene3d-deliveries")
        def deliveries() -> list[dict[str, str]]:
            root = jobs.root / "scene3d"
            results = list(root.glob("*/job/delivery.json"))
            results += list(root.glob("*/job/attachment/delivery.json"))
            return [
                {
                    "url": f"/scene3d-results/{path.relative_to(root).parts[0]}/",
                    "status": "pending_manual_acceptance",
                }
                for path in results
            ]

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
                    path = root / "world.json"
                    path.write_bytes(raw)
                    try:
                        self._process = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "pastport_pdf_vr.cli",
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
                self._process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pastport_pdf_vr.cli",
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
                run_id = uuid4().hex
                root = jobs.root / "scene3d" / run_id
                root.mkdir(parents=True)
                (root / "generation-options.json").write_text(
                    json.dumps(
                        {
                            "job_id": job_id,
                            "scene_id": scene_id,
                            "model": model,
                            "credit_budget": int(budget),
                        }
                    )
                )
            return await generate_job(run_id)

        @app.post("/api/scene3d-resume/{run_id}")
        async def resume(run_id: str) -> dict[str, str]:
            return await generate_job(run_id)

        @app.get("/scene3d-results/{run_id}/")
        async def result(run_id: str) -> RedirectResponse:
            if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
                raise HTTPException(404)
            root = jobs.root / "scene3d" / run_id / "job" / "result"
            if not (root / "scene3d/attachment.json").is_file():
                root = jobs.root / "scene3d" / run_id / "job/attachment/result"
            if not (root / "scene3d/attachment.json").is_file():
                raise HTTPException(404, "3D result unavailable")
            port = await previews.ensure(root)
            return RedirectResponse(f"http://127.0.0.1:{port}/scene3d/index.html")

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
