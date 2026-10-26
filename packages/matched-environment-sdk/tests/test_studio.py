"""Upload boundaries and interruption handling, without model execution."""

from __future__ import annotations

import base64
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from pastport_matched_environment.api.studio import StudioApplication
from pastport_matched_environment.application.inputs import InputValidationError
from pastport_matched_environment.application.studio import (
    StudioJobs,
    prepare_tour,
    safe_relative_name,
)
from pastport_matched_environment.domain.studio import StudioJob, StudioOptions


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
        return 1

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


class StudioTests(unittest.TestCase):
    def test_standalone_museum_does_not_offer_an_unmounted_style_portal(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(StudioApplication(Path(folder)).app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('href="/stylization"', response.text)
                self.assertEqual(client.get("/stylization").status_code, 404)

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
                with patch("pastport_matched_environment.api.studio.MIB", 1):
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
                with patch(
                    "pastport_matched_environment.api.studio.shutil.which", return_value=None
                ):
                    response = client.post("/api/jobs", headers={"X-PastPort-Edit": "1"})
                    self.assertEqual(response.status_code, 503)
