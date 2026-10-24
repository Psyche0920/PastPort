"""Whole fixed build with explicit semantic fixtures; no provider/accuracy claim."""

import base64
import io
import json
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.api.server import LocalReviewApplication
from pastport_pdf_vr.application.automatic_build import AutomaticBuildWorkflow
from pastport_pdf_vr.domain.build import PDFMatchPayload, PDFMatchRequest, PDFObjectMatch
from pastport_pdf_vr.domain.editorial import PositionEdit, TextEdit
from pastport_pdf_vr.domain.evidence import (
    EvidenceClaim,
    EvidencePayload,
    EvidenceScope,
    EvidenceSelection,
    HistoricalSubject,
)
from pastport_pdf_vr.domain.execution import (
    ExecutionInput,
    ExecutionOutput,
    SDKReadiness,
    SubscriptionGrant,
)
from pastport_pdf_vr.domain.geometry import AnchorPosition, PixelPoint
from pastport_pdf_vr.domain.models import DomainModel
from pastport_pdf_vr.domain.pdf import PDFExtractionStatus, PDFPageDraft
from pastport_pdf_vr.domain.recognition import (
    EntityProposal,
    PixelRegion,
    SceneInspectionPayload,
    SceneInspectionRequest,
    SightingProposal,
)
from pastport_pdf_vr.domain.tour import ImportedTour


class FixturePDFReader:
    version = "explicit-fixture-v1"

    def page_count(self, pdf_path: Path, max_pages: int) -> int:
        return 1

    def iter_pages(
        self,
        pdf_path: Path,
        page_count: int,
        max_render_edge: int,
        max_render_bytes: int,
        render_timeout_seconds: int,
    ) -> Iterator[PDFPageDraft]:
        buffer = io.BytesIO()
        with Image.new("RGB", (400, 400), "white") as image:
            image.save(buffer, format="JPEG")
        yield PDFPageDraft(
            page_index=0,
            page_width=400.0,
            page_height=400.0,
            original_text="The doorway has a stone inscription.",
            normalized_text="The doorway has a stone inscription.",
            text_lines=(),
            image_regions=(),
            extraction_status=PDFExtractionStatus.TEXT_EXTRACTED,
            rendered_jpeg=buffer.getvalue(),
        )


class FixtureBuildTransport:
    def __init__(self) -> None:
        self.calls = 0

    def readiness(self, model_id: str) -> SDKReadiness:
        return SDKReadiness(
            authenticated=True,
            auth_mode="chatgpt",
            requested_model=model_id,
            model_available=True,
            image_input_supported=True,
        )

    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        self.calls += 1
        payload: DomainModel
        if request.kind == "scene_inspection":
            scene = SceneInspectionRequest.model_validate_json(request.payload_json)
            payload = SceneInspectionPayload(
                entities=(
                    EntityProposal(
                        proposal_id="door:new",
                        label="Doorway",
                        category="door",
                        distinguishing_features=("Explicit fixture feature",),
                    ),
                ),
                sightings=(
                    SightingProposal(
                        target_ref="door:new",
                        image_id=scene.images[0].image_id,
                        disposition="located",
                        point=PixelPoint(x=1000.0, y=500.0),
                        region=PixelRegion(
                            top_left=PixelPoint(x=990.0, y=490.0),
                            bottom_right=PixelPoint(x=1010.0, y=510.0),
                        ),
                        basis=("Fixture",),
                    ),
                ),
            )
        elif request.kind == "pdf_matching":
            selection = PDFMatchRequest.model_validate_json(request.payload_json)
            page = selection.pages[0]
            payload = PDFMatchPayload(
                matches=(
                    PDFObjectMatch(
                        object_id=selection.objects[0].object_id,
                        subject=HistoricalSubject(
                            subject_id="portal", label="Doorway", retrieval_terms=("inscription",)
                        ),
                        page_index=0,
                        region=PixelRegion(
                            top_left=PixelPoint(x=20.0, y=20.0),
                            bottom_right=PixelPoint(x=200.0, y=200.0),
                        ),
                        passage_ids=(page.passages[0].passage_id,),
                        relationship="same_object",
                        target_scale="component",
                        source_scale="component",
                        story_support="descriptive_only",
                        basis="Explicit fixture mapping, not evidence of visual correctness",
                    ),
                )
            )
        else:
            evidence = EvidenceSelection.model_validate_json(request.payload_json)
            payload = EvidencePayload(
                associations=(),
                claims=(
                    EvidenceClaim(
                        claim_id="claim:inscription",
                        subject_id=evidence.subject.subject_id,
                        scope=EvidenceScope.DIRECT,
                        statement="The doorway has a stone inscription.",
                        passage_ids=(evidence.passages[0].passage_id,),
                    ),
                ),
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


class AutomaticBuildTests(unittest.TestCase):
    def test_pdf_tour_to_editable_vr_and_idempotent_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "source.pdf"
            pdf.write_bytes(b"%PDF-1.7\nexplicit fixture")
            buffer = io.BytesIO()
            with Image.new("RGB", (64, 32), "blue") as image:
                image.save(buffer, format="JPEG")
            uri = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
            tour = root / "index.html"
            tour.write_text(
                '<script id="tour-data" type="application/json">'
                + json.dumps(
                    {
                        "schemaVersion": 4,
                        "id": "tour:test",
                        "firstSceneId": "view:1",
                        "scenes": [{"id": "view:1", "name": "Point 1", "panorama": {"data": uri}}],
                    }
                )
                + "</script>"
            )
            grant = SubscriptionGrant(project_id="build-test", grant_ref="build:1", max_calls=8)
            transport = FixtureBuildTransport()
            workspace = root / "build"
            workflow = AutomaticBuildWorkflow(FixturePDFReader(), transport)
            workflow.run(pdf, tour, workspace, grant, "run:1")
            self.assertEqual(transport.calls, 3)
            repository = SQLiteEditorialRepository(workspace / "editorial.sqlite3")
            snapshot = repository.snapshot(grant.project_id)
            self.assertEqual((len(snapshot.objects), len(snapshot.anchors)), (1, 1))
            self.assertEqual(
                snapshot.objects[0].introduction, "The doorway has a stone inscription."
            )
            evidence = snapshot.objects[0].object.replay_evidence
            assert evidence is not None
            self.assertEqual(evidence.quote_representation, "raw_page")
            self.assertEqual(evidence.passages[0].start, 0)
            obj = snapshot.objects[0]
            assert obj.object.historical_subject_id is not None
            repository.save_text(
                grant.project_id,
                TextEdit(
                    operation_id="human:text",
                    object_id=obj.object.entity.object_id,
                    historical_subject_id=obj.object.historical_subject_id,
                    expected_version=0,
                    introduction="Human corrected text",
                ),
            )
            row = snapshot.anchors[0]
            repository.save_position(
                grant.project_id,
                PositionEdit(
                    operation_id="human:anchor",
                    object_id=row.anchor.object_id,
                    view_id=row.anchor.view_id,
                    panorama=row.anchor.panorama,
                    panorama_revision=1,
                    expected_version=0,
                    position=AnchorPosition(yaw=15.0, pitch=-10.0),
                ),
            )
            workflow.run(pdf, tour, workspace, grant, "run:1")
            workflow.run(pdf, tour, workspace, grant, "run:2")
            latest = repository.snapshot(grant.project_id)
            self.assertEqual(transport.calls, 3)
            self.assertEqual(latest.objects[0].introduction, "Human corrected text")
            self.assertEqual(latest.anchors[0].position.yaw, 15.0)
            admitted = ImportedTour.model_validate_json((workspace / "tour.json").read_bytes())
            with TestClient(
                LocalReviewApplication(
                    grant.project_id, admitted, repository, LocalAssetStore(workspace / "assets")
                ).app
            ) as client:
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/vr/").status_code, 200)
                self.assertEqual(
                    client.get("/api/snapshot").json()["objects"][0]["introduction"],
                    "Human corrected text",
                )
