"""Photo-first preparation, real report rendering, safe uploads and cached identities."""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.api.studio import StudioApplication
from pastport_pdf_vr.application.photo_mapping import PhotoMappingBundle, PhotoMappingWorkflow
from pastport_pdf_vr.application.photos import PhotoInputError, PhotoRegistrar
from pastport_pdf_vr.domain.execution import ExecutionInput, ExecutionOutput, SubscriptionGrant
from pastport_pdf_vr.domain.geometry import PixelPoint
from pastport_pdf_vr.domain.photos import (
    PhotoInspectionPayload,
    PhotoInspectionRequest,
    PhotoSighting,
)
from pastport_pdf_vr.domain.recognition import EntityProposal, PixelRegion
from pastport_pdf_vr.domain.studio import StudioOptions
from tests.test_automatic_build import FixtureBuildTransport, FixturePDFReader
from tests.test_studio import wait_job


class PhotoFixtureTransport(FixtureBuildTransport):
    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        if request.kind != "photo_inspection":
            return super().execute(request, timeout_seconds)
        self.calls += 1
        selection = PhotoInspectionRequest.model_validate_json(request.payload_json)
        existing = selection.catalog[0].object_id if selection.catalog else None
        key = existing or "door:new"
        result = PhotoInspectionPayload(
            entities=()
            if existing
            else (
                EntityProposal(
                    proposal_id=key,
                    label="Doorway",
                    category="door",
                    distinguishing_features=("Explicit fixture feature",),
                ),
            ),
            sightings=tuple(
                PhotoSighting(
                    target_ref=key,
                    photo_id=p.photo_id,
                    region=PixelRegion(
                        top_left=PixelPoint(x=10.0, y=10.0), bottom_right=PixelPoint(x=80.0, y=80.0)
                    ),
                    basis="Explicit offline fixture correspondence",
                )
                for p in selection.photos
            ),
        )
        return ExecutionOutput(
            payload_json=result.model_dump_json(),
            receipt_ref="fixture:photo",
            thread_ref="fixture:thread",
            turn_ref="fixture:turn",
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
        )


class PhotoFixtureRunner:
    def __init__(self) -> None:
        self.transport = PhotoFixtureTransport()

    async def run(
        self,
        pdf: Path,
        tour: Path,
        grant: Path,
        workspace: Path,
        job_id: str,
        options: StudioOptions,
    ) -> int:
        await asyncio.to_thread(
            PhotoMappingWorkflow(FixturePDFReader(), self.transport).run,
            pdf,
            tour,
            workspace,
            SubscriptionGrant.model_validate_json(grant.read_bytes()),
            job_id,
            options.large_pdf,
        )
        return 0

    async def close(self) -> None:
        return None


def photo_bytes(colour: str) -> bytes:
    buffer = io.BytesIO()
    with Image.new("RGB", (120, 160), colour) as image:
        image.save(buffer, "JPEG")
    return buffer.getvalue()


class PhotoMappingTests(unittest.TestCase):
    def test_two_photos_one_identity_report_and_no_redispatch_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = root / "photos"
            photos.mkdir()
            for name, colour in [("one.jpg", "blue"), ("two.jpg", "green")]:
                (photos / name).write_bytes(photo_bytes(colour))
            pdf = root / "source.pdf"
            pdf.write_bytes(b"%PDF-1.7 explicit fixture")
            workspace = root / "result"
            grant = SubscriptionGrant(project_id="photo-test", grant_ref="photo:1", max_calls=10)
            transport = PhotoFixtureTransport()
            workflow = PhotoMappingWorkflow(FixturePDFReader(), transport)
            workflow.run(pdf, photos, workspace, grant, "run:1")
            bundle = PhotoMappingBundle.model_validate_json(
                (workspace / "mapping.json").read_bytes()
            )
            self.assertEqual((len(bundle.objects), len(bundle.inventory.observations)), (1, 2))
            self.assertEqual(len(bundle.objects[0].photo_observations), 2)
            self.assertTrue(bundle.objects[0].historical_subject_id)
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(workspace / "mapping.pdf").pages
            )
            self.assertIn("one.jpg", text)
            self.assertIn("two.jpg", text)
            self.assertIn("The doorway has a stone inscription.", text)
            calls = transport.calls
            workflow.run(pdf, photos, workspace, grant, "run:1")
            workflow.run(pdf, photos, workspace, grant, "run:2")
            self.assertEqual(transport.calls, calls)
            repeated = PhotoMappingBundle.model_validate_json(
                (workspace / "mapping.json").read_bytes()
            )
            self.assertEqual(bundle.objects[0].entity, repeated.objects[0].entity)

    def test_browser_photos_need_no_tour_and_download_only_registered_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = PhotoFixtureRunner()
            with TestClient(StudioApplication(Path(directory), runner).app) as client:
                options = {
                    "title": "Photo fixture",
                    "workflow": "photo_mapping",
                    "mapping_mode": "demo_substitution",
                    "authorize_model": True,
                }
                result = client.post(
                    "/api/jobs",
                    headers={"X-PastPort-Edit": "1"},
                    data={"options": json.dumps(options)},
                    files=[
                        ("document", ("source.pdf", b"%PDF-1.7 fixture")),
                        ("photos", ("one.jpg", photo_bytes("blue"))),
                        ("photos", ("two.jpg", photo_bytes("green"))),
                    ],
                )
                self.assertEqual(result.status_code, 202, result.text)
                job = wait_job(client)
                self.assertIn(job.status, ("completed", "completed_with_gaps"))
                base = f"/projects/{job.project_id}"
                self.assertEqual(
                    client.get(base + "/mapping.pdf").headers["content-type"], "application/pdf"
                )
                bundle = PhotoMappingBundle.model_validate_json(
                    client.get(base + "/mapping.json").content
                )
                observation = bundle.objects[0].photo_observations[0]
                self.assertEqual(
                    client.get(base + "/media/" + observation.crop.asset.sha256).status_code, 200
                )
                self.assertEqual(client.get(base + "/media/" + "0" * 64).status_code, 404)
                self.assertEqual(client.get(base + "/vr/").status_code, 409)

    def test_duplicate_content_and_non_images_fail_before_model_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = LocalAssetStore(root / "assets")
            a = root / "a.jpg"
            b = root / "b.jpg"
            a.write_bytes(photo_bytes("blue"))
            b.write_bytes(a.read_bytes())
            with self.assertRaises(PhotoInputError):
                PhotoRegistrar(assets).register("project", (a, b))
            b.write_bytes(b"not an image")
            with self.assertRaises(PhotoInputError):
                PhotoRegistrar(assets).register("project", (b,))
