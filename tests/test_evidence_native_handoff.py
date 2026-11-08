"""Typed Evidence reaches environment review without a PDF reread or quote rewriting."""

import base64
import hashlib
import io
import json
import sqlite3
from pathlib import Path
from typing import Any
import subprocess
from unittest.mock import patch

import pytest
from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.environment_handoff import EvidenceEnvironmentHandoff, normalized
from pastport_evidence.application.evidence import CorpusIndex
from pastport_evidence.application.pdf_ingestion import PDFIngestionService
from pastport_evidence.application.photo_mapping import PreparedDocuments
from pastport_evidence.application.photos import PhotoRegistrar
from pastport_evidence.domain.geometry import PixelPoint
from pastport_evidence.domain.mapping import MappedObject, SourceEvidence
from pastport_evidence.domain.models import ProcessingLimits
from pastport_evidence.domain.photos import PhotoInventory, PhotoObservation
from pastport_evidence.domain.recognition import PixelRegion, SceneEntity
from pastport_matched_environment.application.candidate_source import PDFCandidateSource
from pastport_matched_environment.application.idml_environment import IDMLEnvironmentWorkflow
from pastport_matched_environment.domain.execution import (
    ExecutionInput,
    ExecutionOutput,
    SDKReadiness,
    SubscriptionGrant,
)
from PIL import Image
from test_pdf_text_ocr import CountingReader, FakeOCR, executable, mixed_pdf


class Transport:
    def __init__(self) -> None:
        self.calls: list[ExecutionInput] = []

    def readiness(self, model_id: str) -> SDKReadiness:
        return SDKReadiness(authenticated=True, auth_mode="chatgpt", requested_model=model_id, model_available=True, image_input_supported=True)

    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        self.calls.append(request)
        raw = json.loads(request.payload_json)
        assert "source_scene_id" in raw, "Typed handoff must not invoke semantic PDF inspection"
        payload = (
            {"objects": [{"number": 12, "verdict": "confirmed", "reason": "Synthetic point"}]}
            if raw.get("proposals")
            else {
                "objects": [
                    {
                        "number": 12,
                        "status": "visible",
                        "projection_index": 0,
                        "center": [0.5, 0.5],
                        "basis": "Synthetic point",
                    }
                ]
            }
        )
        return ExecutionOutput(
            payload_json=json.dumps(payload),
            receipt_ref="fixture-receipt",
            thread_ref="fixture-thread",
            turn_ref="fixture-turn",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
        )


def test_verified_pdf_rows_reach_environment_without_any_pdf_tool(tmp_path: Path) -> None:
    pdf = tmp_path / "original.pdf"
    mixed_pdf(pdf)
    assets = LocalAssetStore(tmp_path / "assets")
    source = PDFIngestionService(
        assets, CountingReader(executable(), FakeOCR())
    ).register_and_extract("fixture", pdf, ProcessingLimits())
    photo_file = tmp_path / "photo.jpg"
    with Image.new("RGB", (400, 200), "red") as image:
        image.save(photo_file)
    photo = PhotoRegistrar(assets).register("fixture", (photo_file,))[0]
    entity = SceneEntity(
        object_id="fixture-object",
        display_number=12,
        label="Fixture whole",
        category="fixture",
        distinguishing_features=("Red fixture",),
    )
    observation = PhotoObservation(
        object_id=entity.object_id,
        photo=photo,
        region=PixelRegion(
            top_left=PixelPoint(x=0.0, y=0.0), bottom_right=PixelPoint(x=400.0, y=200.0)
        ),
        crop=photo.image,
        identity_state="confirmed",
        basis="Synthetic same-object observation",
    )
    passage = CorpusIndex(source).passages[0]
    evidence = SourceEvidence(
        historical_subject_id="fixture-history",
        title="Historical source",
        pdf_page_number=1,
        printed_page=None,
        original_quote=passage.quote,
        translation="",
        scope="Source exact",
        limitation="Unreviewed synthetic association",
        source_page_sha256=hashlib.sha256(source.pages[0].original_text.encode()).hexdigest(),
        quote_representation="raw_page",
        source_ref=source.source,
        passages=(passage,),
        source_image_role="text_evidence",
    )
    bundle = PreparedDocuments(
        project_id="fixture",
        input_binding="synthetic-input",
        source=source.source,
        inventory=PhotoInventory(photos=(photo,), entities=(entity,), observations=(observation,)),
        objects=(
            MappedObject(
                entity=entity,
                historical_subject_id="fixture-history",
                source_evidence=evidence,
                photo_observations=(observation,),
            ),
        ),
        gaps=(),
    )
    transport = Transport()
    exporter = EvidenceEnvironmentHandoff(assets)
    original_run = subprocess.run

    def bounded(args: list[str], *values: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert args[0] not in ("pdftoppm", "pdftotext"), "Verified PDF handoff invoked a PDF tool"
        return original_run(args, *values, **kwargs)

    with patch("subprocess.run", bounded):
        handoff = exporter.export(tmp_path / "handoffs", bundle, source)
        saved = PDFCandidateSource(handoff)
        assert saved.count == 3 and saved.text(1) == source.pages[0].original_text
        buffer = io.BytesIO()
        with Image.new("RGB", (400, 200), "red") as image:
            image.save(buffer, format="JPEG")
        (tmp_path / "scene").mkdir()
        (tmp_path / "scene/raw-scene.json").write_text(
            '{"schema_version":"pastport.raw-scene/1.0"}'
        )
        tour = tmp_path / "tour.html"
        tour.write_text(
            '<script id="tour-data" type="application/json">'
            + json.dumps(
                {
                    "schemaVersion": 4,
                    "id": "fixture",
                    "firstSceneId": "one",
                    "scenes": [
                        {
                            "id": "one",
                            "name": "one",
                            "panorama": {
                                "data": "data:image/jpeg;base64,"
                                + base64.b64encode(buffer.getvalue()).decode(),
                                "width": 400,
                                "height": 200,
                                "source": "Fixture",
                            },
                            "view": {"yaw": 0.0, "pitch": 0.0, "hfov": 90},
                            "hotspots": [],
                        }
                    ],
                }
            )
            + "</script>"
        )
        grant = SubscriptionGrant(
            project_id="fixture", grant_ref="fixture-native", max_calls=4, max_recorded_tokens=1000
        )
        output = IDMLEnvironmentWorkflow(transport).run(
            handoff, tour, tmp_path / "environment", "fixture-native", grant
        )
        assert len(transport.calls) == 2
        IDMLEnvironmentWorkflow(transport).run(
            handoff, tour, tmp_path / "environment", "fixture-native", grant
        )
        assert len(transport.calls) == 2
    assert (output / "source.pdf").read_bytes() == pdf.read_bytes()
    assert (output / "source-text.json").is_file()
    with sqlite3.connect(output / "pastport_matching.sqlite3") as db:
        assert db.execute("select exact_text from passages").fetchone()[0] == normalized(
            passage.quote
        )
    quotes = json.loads((handoff / "quote-regions.json").read_text())
    assert quotes[0]["line_start"] == 1 and quotes[0]["line_end"] == 2
    assert exporter.export(tmp_path / "handoffs", bundle, source) == handoff
    (handoff / "source-text.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        exporter.validate(handoff)
