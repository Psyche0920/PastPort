"""Financial regression checks: submission replay and source backup, without providers."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from collections.abc import Awaitable, Callable
from contextlib import closing
from pathlib import Path
from typing import cast
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from pydantic import SecretStr
from starlette.types import Message

from pastport_pdf_vr.api.scene3d_studio import Scene3DPortal
from pastport_pdf_vr.application.marble_generation import MarbleGeneration
from pastport_pdf_vr.application.reference_preview import ReferencePreviewPool
from pastport_pdf_vr.application.scene3d import Scene3DAttachment
from pastport_pdf_vr.application.studio import StudioJobs, SubprocessBuildRunner
from pastport_pdf_vr.domain.environment import RunResultPointer
from pastport_pdf_vr.domain.studio import StudioJob


class SettledProcess:
    returncode: int | None = 0

    async def wait(self) -> int:
        return 0


async def settled_process(*args: object, **kwargs: object) -> SettledProcess:
    return SettledProcess()


def generation_request() -> Request:
    body = urlencode(
        {
            "job_id": "a" * 32,
            "scene_id": "view-1",
            "model": "marble-1.1",
            "credit_budget": "1500",
            "authorize": "yes",
        }
    ).encode()

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
            "path": "/api/scene3d-generate",
        },
        receive,
    )


class Scene3DSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_frontend_post_reuses_durable_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            jobs = StudioJobs(Path(directory), SubprocessBuildRunner())
            job = StudioJob(
                job_id="a" * 32, project_id="b" * 32, title="Submission fixture", status="completed"
            )
            jobs.save(job)
            run = jobs.root / "projects" / job.project_id / "runs" / job.job_id
            run.mkdir(parents=True)
            (run / "result-pointer.json").write_text(
                RunResultPointer(
                    project_id=job.project_id,
                    source_binding="0" * 64,
                    grant_binding="0" * 64,
                    result_run_id=job.job_id,
                ).model_dump_json()
            )
            app = FastAPI()
            portal = Scene3DPortal(app, jobs, ReferencePreviewPool())
            portal._api_key = SecretStr("offline-placeholder-not-a-provider-key")
            endpoint = cast(
                Callable[[Request], Awaitable[dict[str, str]]],
                next(
                    route.endpoint
                    for route in app.routes
                    if isinstance(route, APIRoute) and route.path == "/api/scene3d-generate"
                ),
            )
            with patch(
                "pastport_pdf_vr.api.scene3d_studio.asyncio.create_subprocess_exec",
                side_effect=settled_process,
            ):
                first = await endpoint(generation_request())
                second = await endpoint(generation_request())
            self.assertEqual(first["resume"], second["resume"])
            self.assertEqual(
                len(list((jobs.root / "scene3d").glob("*/generation-options.json"))), 1
            )

    def test_new_directory_cannot_repeat_a_paid_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "result"
            source.mkdir()
            first, second = root / "first", root / "second"
            MarbleGeneration.claim_source(source, first, "0" * 64)
            MarbleGeneration.claim_source(source, first, "0" * 64)
            with self.assertRaises(RuntimeError):
                MarbleGeneration.claim_source(source, second, "0" * 64)

    def test_frozen_backup_creates_parent_and_preserves_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with closing(sqlite3.connect(source / "pastport_matching.sqlite3")) as db, db:
                db.execute("CREATE TABLE human_data(value TEXT)")
                db.execute("INSERT INTO human_data VALUES ('retained human edit')")
            attachment = Scene3DAttachment(
                source, source / "unused-world.json", root / "new" / "frozen", "view-1"
            )
            attachment.preserve()
            with closing(sqlite3.connect(attachment.output / "pastport_matching.sqlite3")) as db:
                self.assertEqual(
                    db.execute("SELECT value FROM human_data").fetchone(), ("retained human edit",)
                )
