"""Offline replay is explicitly supplied data, not a recognition benchmark."""

import base64
import hashlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.adapters.tour import TourImporter, TourImportError
from pastport_pdf_vr.api.server import LocalReviewApplication
from pastport_pdf_vr.application.bootstrap import ReplayWorkflow
from pastport_pdf_vr.domain.editorial import PositionEdit, PreviewSnapshot, TextEdit
from pastport_pdf_vr.domain.geometry import AnchorPosition
from pastport_pdf_vr.domain.models import ProcessingLimits
from pastport_pdf_vr.domain.tour import ImportedTour


class LocalReplayTests(unittest.TestCase):
    def test_tour_replay_api_edits_and_repeat_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = io.BytesIO()
            Image.new("RGB", (64, 32), (30, 90, 110)).save(image, format="JPEG")
            uri = "data:image/jpeg;base64," + base64.b64encode(image.getvalue()).decode()
            scenes = [
                {
                    "id": name,
                    "name": name,
                    "panorama": {"data": uri},
                    "hotspots": [{"type": "scene", "targetId": other, "yaw": 10.0}],
                }
                for name, other in (("view:1", "view:2"), ("view:2", "view:1"))
            ]
            payload = {
                "schemaVersion": 4,
                "id": "tour:test",
                "firstSceneId": "view:1",
                "scenes": scenes,
            }
            tour_path = root / "index.html"
            tour_path.write_text(
                '<script>alert("never executed")</script>'
                '<script id="tour-data" type="application/json">'
                + json.dumps(payload)
                + "</script>"
            )
            report_path = root / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "input_html_sha256": hashlib.sha256(tour_path.read_bytes()).hexdigest(),
                        "located": [
                            {
                                "object_id": 1,
                                "modern_name": "Door",
                                "historical_id": "portal",
                                "scene_id": scene,
                                "yaw": 0.0,
                                "pitch": 0.0,
                                "panorama_sha256": "legacy-data-uri-hash",
                                "panorama_hash_basis": "data_uri",
                                "basis": "Explicit fixture",
                            }
                            for scene in ("view:1", "view:2")
                        ],
                    }
                )
            )
            limits = ProcessingLimits(max_model_calls=1, budget_usd=Decimal("0.01"))
            workspace = root / "runtime"
            workflow = ReplayWorkflow()
            workflow.run("test", tour_path, report_path, workspace, limits, "run:1")
            tour = ImportedTour.model_validate_json((workspace / "tour.json").read_bytes())
            self.assertEqual(tour.views[0].links[0].target_view_id, "view:2")
            self.assertEqual(tour.views[0].width, 64)
            repo = SQLiteEditorialRepository(workspace / "editorial.sqlite3")
            application = LocalReviewApplication(
                "test", tour, repo, LocalAssetStore(workspace / "assets")
            )
            with TestClient(application.app) as client:
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/vr/").status_code, 200)
                self.assertNotIn('alert("never executed")', client.get("/vr/").text)
                snapshot = PreviewSnapshot.model_validate_json(client.get("/api/snapshot").content)
                self.assertEqual((len(snapshot.objects), len(snapshot.anchors)), (1, 2))
                self.assertEqual(snapshot.mode, "synthetic_replay")
                media = client.get("/media/" + tour.views[0].panorama.asset.sha256)
                self.assertEqual(media.content, image.getvalue())
                self.assertEqual(media.headers["content-type"], "image/jpeg")
                self.assertEqual(client.get("/media/unknown").status_code, 404)
                self.assertEqual(client.get("/editorial.sqlite3").status_code, 404)
                text = TextEdit(
                    operation_id="human:text",
                    object_id="demo-object:01",
                    historical_subject_id="portal",
                    expected_version=0,
                    introduction="Human introduction",
                )
                self.assertEqual(client.post("/api/text", json=text.model_dump()).status_code, 403)
                headers = {"X-PastPort-Edit": "1", "Origin": "http://testserver"}
                self.assertEqual(
                    client.post(
                        "/api/text",
                        json=text.model_dump(),
                        headers={**headers, "Origin": "https://unrelated.example"},
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.post("/api/text", json=text.model_dump(), headers=headers).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(
                        "/api/text",
                        json=text.model_copy(update={"operation_id": "stale:text"}).model_dump(),
                        headers=headers,
                    ).status_code,
                    409,
                )
                anchor = snapshot.anchors[0]
                edit = PositionEdit(
                    operation_id="human:position",
                    object_id=anchor.anchor.object_id,
                    view_id=anchor.anchor.view_id,
                    panorama=anchor.anchor.panorama,
                    panorama_revision=1,
                    expected_version=0,
                    position=AnchorPosition(yaw=25.0, pitch=-12.0),
                )
                self.assertEqual(
                    client.post(
                        "/api/position", json=edit.model_dump(mode="json"), headers=headers
                    ).status_code,
                    200,
                )
                workflow.run("test", tour_path, report_path, workspace, limits, "run:1")
                workflow.run("test", tour_path, report_path, workspace, limits, "run:2")
                latest = PreviewSnapshot.model_validate_json(client.get("/api/snapshot").content)
                self.assertEqual(latest.objects[0].introduction, "Human introduction")
                self.assertEqual(latest.anchors[0].position, edit.position)
                self.assertEqual(latest.anchors[1].origin, "model")
                self.assertEqual(len(latest.anchors), 2)

    def test_unknown_schema_and_escaping_media_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            limits = ProcessingLimits(max_model_calls=1, budget_usd=Decimal("0.01"))
            importer = TourImporter(LocalAssetStore(root / "assets"))
            path = root / "index.html"
            for media, version in (("../outside.jpg", 4), ("image.jpg", 99)):
                path.write_text(
                    '<script id="tour-data" type="application/json">'
                    + json.dumps(
                        {
                            "schemaVersion": version,
                            "id": "tour",
                            "firstSceneId": "one",
                            "scenes": [{"id": "one", "name": "one", "panorama": {"data": media}}],
                        }
                    )
                    + "</script>"
                )
                with self.assertRaises((TourImportError, OSError)):
                    importer.import_html("test", path, limits)
