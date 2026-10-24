"""Browser upload and linked result contracts with explicit offline model counterparts."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import stat
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from pastport_pdf_vr.api.studio import StudioApplication
from pastport_pdf_vr.application.automatic_build import AutomaticBuildWorkflow
from pastport_pdf_vr.application.inputs import InputValidationError
from pastport_pdf_vr.application.studio import StudioJobs, prepare_tour, safe_relative_name
from pastport_pdf_vr.domain.editorial import PreviewSnapshot
from pastport_pdf_vr.domain.execution import ExecutionInput, ExecutionOutput, SubscriptionGrant
from pastport_pdf_vr.domain.geometry import PixelPoint
from pastport_pdf_vr.domain.recognition import (
    PixelRegion,
    SceneInspectionPayload,
    SceneInspectionRequest,
    SightingProposal,
)
from pastport_pdf_vr.domain.studio import StudioJob, StudioOptions
from tests.test_automatic_build import FixtureBuildTransport, FixturePDFReader


class CatalogFixtureTransport(FixtureBuildTransport):
    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        if request.kind == "scene_inspection":
            scene = SceneInspectionRequest.model_validate_json(request.payload_json)
            if scene.catalog:
                targets = scene.target_ids or tuple(entity.object_id for entity in scene.catalog)
                payload = SceneInspectionPayload(
                    sightings=tuple(
                        SightingProposal(
                            target_ref=target,
                            image_id=scene.images[0].image_id,
                            disposition="located",
                            point=PixelPoint(x=1000.0, y=500.0),
                            region=PixelRegion(
                                top_left=PixelPoint(x=990.0, y=490.0),
                                bottom_right=PixelPoint(x=1010.0, y=510.0),
                            ),
                            basis=("Explicit fixture catalog identity",),
                        )
                        for target in targets
                    )
                )
                return ExecutionOutput(
                    payload_json=payload.model_dump_json(),
                    receipt_ref="fixture:transport",
                    thread_ref="fixture:thread",
                    turn_ref="fixture:turn",
                    input_tokens=20,
                    output_tokens=10,
                    total_tokens=30,
                )
        return super().execute(request, timeout_seconds)


class FixtureRunner:
    def __init__(self) -> None:
        self.calls = 0
        self.stopped = False

    async def run(
        self,
        pdf: Path,
        tour: Path,
        grant: Path,
        workspace: Path,
        job_id: str,
        options: StudioOptions,
    ) -> int:
        self.calls += 1
        workflow = AutomaticBuildWorkflow(FixturePDFReader(), CatalogFixtureTransport())
        await asyncio.to_thread(
            workflow.run,
            pdf,
            tour,
            workspace,
            SubscriptionGrant.model_validate_json(grant.read_bytes()),
            job_id,
            options.mapping_mode,
            options.large_pdf,
        )
        return 0

    async def close(self) -> None:
        self.stopped = True


def fixture_tour() -> bytes:
    buffer = io.BytesIO()
    with Image.new("RGB", (64, 32), "blue") as image:
        image.save(buffer, format="JPEG")
    uri = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    payload = {
        "schemaVersion": 4,
        "id": "tour:test",
        "firstSceneId": "view:1",
        "scenes": [{"id": "view:1", "name": "Point 1", "panorama": {"data": uri}}],
    }
    return (
        '<script id="tour-data" type="application/json">' + json.dumps(payload) + "</script>"
    ).encode()


def wait_job(client: TestClient) -> StudioJob:
    for _ in range(150):
        job = StudioJob.model_validate_json(json.dumps(client.get("/api/jobs").json()[0]))
        if job.status != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("Fixture job did not complete")


class StudioTests(unittest.TestCase):
    def test_upload_generates_linked_review_and_preserves_human_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FixtureRunner()
            application = StudioApplication(Path(directory), runner)
            with TestClient(application.app) as client:
                self.assertEqual(client.get("/").status_code, 200)
                self.assertIn("拖入你的 PDF", client.get("/").text)
                capabilities = client.get("/api/capabilities").json()
                self.assertEqual(
                    next(c["status"] for c in capabilities if c["key"] == "model_3d"), "planned"
                )
                project_id = ""
                for iteration in range(2):
                    options = {"title": "Fixture project", "authorize_model": True}
                    if iteration:
                        options["project_id"] = project_id
                    response = client.post(
                        "/api/jobs",
                        headers={"X-PastPort-Edit": "1"},
                        data={"options": json.dumps(options)},
                        files=[
                            ("document", ("source.pdf", b"%PDF-1.7 fixture")),
                            ("tour", ("index.html", fixture_tour())),
                        ],
                    )
                    self.assertEqual(response.status_code, 202, response.text)
                    job = wait_job(client)
                    self.assertIn(job.status, ("completed", "completed_with_gaps"))
                    project_id = job.project_id
                    prefix = "/projects/" + project_id
                    self.assertEqual(client.get(prefix + "/").status_code, 200)
                    self.assertEqual(client.get(prefix + "/vr/").status_code, 200)
                    snapshot = PreviewSnapshot.model_validate_json(
                        client.get(prefix + "/api/snapshot").text
                    )
                    self.assertEqual(len(snapshot.objects), 1)
                    pano = client.get(prefix + "/api/tour").json()["views"][0]["panorama"]["asset"][
                        "sha256"
                    ]
                    self.assertEqual(client.get(prefix + "/media/" + pano).status_code, 200)
                    row = snapshot.objects[0]
                    if not iteration:
                        result = client.post(
                            prefix + "/api/text",
                            headers={"X-PastPort-Edit": "1"},
                            json={
                                "operation_id": "studio-human",
                                "object_id": row.object.entity.object_id,
                                "expected_version": row.version,
                                "historical_subject_id": row.object.historical_subject_id,
                                "introduction": "Human wording",
                                "background": "Human context",
                            },
                        )
                        self.assertEqual(result.status_code, 200, result.text)
                    else:
                        self.assertEqual(row.introduction, "Human wording")
                self.assertEqual(runner.calls, 2)
            self.assertTrue(runner.stopped)

    def test_rejects_cross_origin_unapproved_and_unsupported_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FixtureRunner()
            with TestClient(StudioApplication(Path(directory), runner).app) as client:
                self.assertEqual(client.post("/api/jobs").status_code, 403)
                self.assertEqual(
                    client.post(
                        "/api/jobs",
                        headers={"X-PastPort-Edit": "1", "Origin": "https://other.example"},
                    ).status_code,
                    403,
                )
                for name, content in [("source.idml", b"PK"), ("source.pdf", b"not pdf")]:
                    response = client.post(
                        "/api/jobs",
                        headers={"X-PastPort-Edit": "1"},
                        data={"options": json.dumps({"title": "Invalid", "authorize_model": True})},
                        files=[
                            ("document", (name, content)),
                            ("tour", ("index.html", fixture_tour())),
                        ],
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(runner.calls, 0)
                self.assertEqual(client.get("/api/jobs").json(), [])

    def test_zip_and_directory_keep_relative_paths_and_reject_unsafe_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "good"
            good.mkdir()
            with zipfile.ZipFile(good / "tour.zip", "w") as archive:
                archive.writestr("export/index.html", fixture_tour())
                archive.writestr("export/media/photo.jpg", b"fixture")
            self.assertEqual(prepare_tour(good).name, "index.html")
            for index, name in enumerate(
                ("../escape.html", "/absolute.html", "a\\b.html", "C:/bad.html")
            ):
                folder = root / str(index)
                folder.mkdir()
                with zipfile.ZipFile(folder / "bad.zip", "w") as archive:
                    archive.writestr(name, b"bad")
                with self.assertRaises(InputValidationError):
                    prepare_tour(folder)
            folder = root / "symlink"
            folder.mkdir()
            with zipfile.ZipFile(folder / "bad.zip", "w") as archive:
                info = zipfile.ZipInfo("index.html")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "/secret")
            with self.assertRaises(InputValidationError):
                prepare_tour(folder)
            for name in ("../bad", "x/../bad", "C:/bad", "a\\b", "/bad", "a//b"):
                with self.assertRaises(InputValidationError):
                    safe_relative_name(name)

    def test_restart_marks_interrupted_without_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FixtureRunner()
            jobs = StudioJobs(Path(directory), runner)
            job = StudioJob(
                job_id="a" * 32, project_id="b" * 32, title="Interrupted", status="running"
            )
            jobs.save(job)
            restarted = StudioJobs(Path(directory), runner)
            self.assertEqual(restarted.list()[0].status, "running")
            restarted.recover_interrupted()
            self.assertEqual(restarted.list()[0].status, "recovery_required")
            self.assertEqual(runner.calls, 0)

    def test_request_body_limit_and_reserved_3d_format_do_not_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FixtureRunner()
            with TestClient(StudioApplication(Path(directory), runner).app) as client:
                with patch("pastport_pdf_vr.api.studio.MIB", 1):
                    response = client.post(
                        "/api/jobs", headers={"X-PastPort-Edit": "1"}, data={"options": "x" * 1000}
                    )
                    self.assertEqual(response.status_code, 413, response.text)
                response = client.post(
                    "/api/jobs",
                    headers={"X-PastPort-Edit": "1"},
                    data={
                        "options": json.dumps(
                            {
                                "title": "3D future",
                                "authorize_model": True,
                                "scene_format": "model_3d",
                            }
                        )
                    },
                    files=[
                        ("document", ("source.pdf", b"%PDF-1.7 fixture")),
                        ("tour", ("model.glb", b"fixture")),
                    ],
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(runner.calls, 0)
                self.assertEqual(client.get("/api/jobs").json(), [])

    def test_reports_missing_poppler_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(StudioApplication(Path(directory), FixtureRunner()).app) as client:
                with patch("pastport_pdf_vr.api.studio.shutil.which", return_value=None):
                    response = client.post("/api/jobs", headers={"X-PastPort-Edit": "1"})
                    self.assertEqual(response.status_code, 503)
