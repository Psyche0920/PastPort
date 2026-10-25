"""Behavioral SDK-pipeline and browser checks use explicit semantic counterparts."""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import io
import json
import re
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from pastport_pdf_vr.adapters.structured_output import StrictOutputSchema
from pastport_pdf_vr.api.studio import StudioApplication
from pastport_pdf_vr.application.environment_build import (
    EnvironmentBuildWorkflow,
    PDFBatchInput,
    RelationInput,
    SceneInput,
)
from pastport_pdf_vr.application.studio import SubprocessBuildRunner
from pastport_pdf_vr.domain.environment import (
    HistoricalRelation,
    LocationBatch,
    LocationReview,
    LocationReviews,
    MatchedBatch,
    MatchedObject,
    PageCrop,
    ProposedLocation,
    RelationInventory,
    StructuralVerdict,
)
from pastport_pdf_vr.domain.execution import (
    ExecutionInput,
    ExecutionOutput,
    SDKReadiness,
    SubscriptionGrant,
)
from pastport_pdf_vr.domain.studio import StudioOptions
from tests.test_environment_agent import sample_inputs


class EnvironmentFixtureTransport:
    def __init__(
        self, *, part: bool = False, wrong_quote: bool = False, reject_location: bool = False
    ) -> None:
        self.calls: list[ExecutionInput] = []
        self.part, self.wrong_quote, self.reject_location = part, wrong_quote, reject_location

    def readiness(self, model_id: str) -> SDKReadiness:
        return SDKReadiness(
            authenticated=True,
            auth_mode="chatgpt",
            requested_model=model_id,
            model_available=True,
            image_input_supported=True,
        )

    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        self.calls.append(request)
        for image, sha in zip(request.image_paths, request.image_hashes, strict=True):
            if hashlib.sha256(Path(image).read_bytes()).hexdigest() != sha:
                raise ValueError("Fixture received a changed model image")
        raw = json.loads(request.payload_json)
        payload: (
            MatchedBatch | LocationBatch | LocationReviews | RelationInventory | StructuralVerdict
        )
        if "pages" in raw:
            source = PDFBatchInput.model_validate_json(request.payload_json)
            quote = (
                "Invented unsupported sentence."
                if self.wrong_quote
                else source.pages[0].native_text
            )
            whole = MatchedObject(
                number=27,
                name="Labeled fixture whole",
                boundary="Entire fixture whole",
                history_key="fixture-whole",
                history="Documented fixture whole",
                parent="Fixture site",
                page=1,
                quote=quote,
                historical_image=None,
                modern_images=(
                    PageCrop(page=1, box=(0.05, 0.1, 0.8, 0.8), basis="Explicit fixture region"),
                ),
                explanation="Explicit offline counterpart",
                proxy="Synthetic proxy",
                limitation="Not real recognition",
                whole_number=None,
                historical_relation=None,
            )
            if source.expected_entries:
                entry = source.expected_entries[0]
                whole = whole.model_copy(
                    update={
                        "number": entry.number,
                        "history_key": entry.history_key,
                        "page": entry.detail_page,
                    }
                )
            objects: tuple[MatchedObject, ...] = (whole,)
            if self.part:
                objects += (
                    whole.model_copy(
                        update={
                            "number": 91,
                            "name": "Fixture part proxy",
                            "history_key": "fixture-part",
                            "history": "Documented fixed part",
                            "whole_number": 27,
                            "historical_relation": "fixed_part_of",
                        }
                    ),
                )
            payload = MatchedBatch(objects=objects, gaps=())
        elif "source_scene_id" in raw:
            scene = SceneInput.model_validate_json(request.payload_json)
            if scene.proposals:
                payload = LocationReviews(
                    objects=tuple(
                        LocationReview(
                            number=o.number,
                            verdict="rejected" if self.reject_location else "confirmed",
                            reason="Independent explicit fixture audit",
                        )
                        for o in scene.objects
                    )
                )
            else:
                payload = LocationBatch(
                    objects=tuple(
                        ProposedLocation(
                            number=o.number,
                            status="visible",
                            projection_index=0,
                            center=(0.3 if o.number == 27 else 0.8, 0.5),
                            basis="New fixture view point; no imported hotspots",
                        )
                        for o in scene.objects
                    )
                )
        else:
            relation = RelationInput.model_validate_json(request.payload_json)
            if relation.relation:
                payload = StructuralVerdict(
                    modern_relation="unrelated",
                    verdict="rejected",
                    reason="Part proxy is spatially separate from whole proxy in explicit fixture",
                )
            else:
                payload = RelationInventory(
                    relations=(
                        (
                            HistoricalRelation(
                                whole_object_number=27,
                                part_object_number=91,
                                historical_relation="fixed_part_of",
                                reason="Fixture hierarchy",
                            ),
                        )
                        if self.part
                        else ()
                    ),
                    review_basis="Complete fixture catalog inspected",
                )
        return ExecutionOutput(
            payload_json=payload.model_dump_json(),
            receipt_ref="fixture:semantic",
            thread_ref="fixture:thread",
            turn_ref=f"fixture:{len(self.calls)}",
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
        )


class EnvironmentFixtureRunner:
    def __init__(self, transport: EnvironmentFixtureTransport) -> None:
        self.transport = transport

    async def run(
        self,
        pdf: Path,
        tour: Path,
        grant: Path,
        workspace: Path,
        job_id: str,
        options: StudioOptions,
    ) -> int:
        binary = shutil.which("pdftoppm")
        assert binary is not None
        await asyncio.to_thread(
            EnvironmentBuildWorkflow(Path(binary), self.transport).run,
            pdf,
            tour,
            SubscriptionGrant.model_validate_json(grant.read_bytes()),
            workspace,
            job_id,
            title=options.title,
            large_pdf=options.large_pdf,
        )
        return 0

    async def close(self) -> None:
        pass


@unittest.skipUnless(shutil.which("pdftoppm") and shutil.which("pdftotext"), "Poppler required")
class EnvironmentBuildTests(unittest.TestCase):
    def build(
        self,
        root: Path,
        *,
        views: int = 1,
        transport: EnvironmentFixtureTransport | None = None,
        max_calls: int = 20,
    ) -> tuple[EnvironmentFixtureTransport, Path, Path, Path]:
        pdf, tour = sample_inputs(root, "new-input", views)
        transport = transport or EnvironmentFixtureTransport()
        workspace = root / "workspace"
        binary = shutil.which("pdftoppm")
        assert binary is not None
        EnvironmentBuildWorkflow(Path(binary), transport).run(
            pdf,
            tour,
            SubscriptionGrant(
                project_id="fixture",
                grant_ref="fixture:grant",
                max_calls=max_calls,
                max_recorded_tokens=10000,
            ),
            workspace,
            "run-one",
        )
        return transport, workspace, pdf, tour

    def test_new_view_counts_and_receipt_reuse(
        self,
    ) -> None:
        for count in (1, 3):
            with self.subTest(views=count), tempfile.TemporaryDirectory() as directory:
                transport, workspace, pdf, tour = self.build(Path(directory), views=count)
                output = workspace / "runs/run-one/result"
                report = json.loads((output / "vr_trial/trial_report.json").read_text())
                self.assertEqual(report["viewpoint_count"], count)
                self.assertEqual(report["hotspot_count"], count)
                self.assertNotIn("old-answer", (output / "vr_trial/index.html").read_text())
                calls = len(transport.calls)
                binary = shutil.which("pdftoppm")
                assert binary is not None
                EnvironmentBuildWorkflow(Path(binary), transport).run(
                    pdf,
                    tour,
                    SubscriptionGrant(
                        project_id="fixture",
                        grant_ref="fixture:grant",
                        max_calls=20,
                        max_recorded_tokens=10000,
                    ),
                    workspace,
                    "run-one",
                )
                self.assertEqual(len(transport.calls), calls)
                with sqlite3.connect(output / "pastport_matching.sqlite3") as db:
                    self.assertEqual(
                        db.execute("SELECT count(*) FROM modern_objects").fetchone(), (1,)
                    )
                (pdf).write_bytes(b"%PDF-changed")
                with self.assertRaises(ValueError):
                    EnvironmentBuildWorkflow(Path(binary), transport).run(
                        pdf,
                        tour,
                        SubscriptionGrant(
                            project_id="fixture",
                            grant_ref="fixture:grant",
                            max_calls=20,
                            max_recorded_tokens=10000,
                        ),
                        workspace,
                        "run-one",
                    )
                self.assertEqual(len(transport.calls), calls)

    def test_semantic_relation_discovery_excludes_spatially_unrelated_part(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, workspace, _, _ = self.build(
                Path(directory), transport=EnvironmentFixtureTransport(part=True)
            )
            run = workspace / "runs/run-one"
            relation = json.loads((run / "locations.json").read_text())["relationship_reviews"][0]
            self.assertEqual(relation["verdict"], "rejected")
            self.assertEqual(relation["part_object_number"], 91)
            report = json.loads((run / "result/vr_trial/trial_report.json").read_text())
            self.assertEqual({row["object_id"] for row in report["located"]}, {27})
            self.assertTrue((run / "relation-discovery.json").is_file())
            with (run / "result/expanded_mapping.csv").open() as stream:
                rows = {int(row["object_number"]): row for row in csv.DictReader(stream)}
            self.assertEqual(rows[91]["review_state"], "invalid_structural_relation")
            self.assertEqual(rows[27]["review_state"], "candidate_unreviewed")

    def test_unsupported_quote_or_insufficient_review_budget_stops_publication(
        self,
    ) -> None:
        for transport, calls in (
            (EnvironmentFixtureTransport(wrong_quote=True), 20),
            (EnvironmentFixtureTransport(), 1),
        ):
            with self.subTest(calls=calls), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaises(ValueError):
                    self.build(root, transport=transport, max_calls=calls)
                self.assertFalse((root / "workspace/runs/run-one/result").exists())
                with sqlite3.connect(root / "workspace/codex-executions.sqlite3") as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM executions").fetchone(), (1,))

    def test_rejected_overlay_proposals_do_not_become_hotspots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, workspace, _, _ = self.build(
                Path(directory), transport=EnvironmentFixtureTransport(reject_location=True)
            )
            run = workspace / "runs/run-one"
            report = json.loads((run / "result/vr_trial/trial_report.json").read_text())
            self.assertEqual(report["hotspot_count"], 0)
            self.assertTrue(list(run.glob("audit-*.jpg")))

    def test_browser_upload_routes_to_owned_reference_runtime(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "browser-input", 1)
            transport = EnvironmentFixtureTransport()
            application = StudioApplication(root / "studio", EnvironmentFixtureRunner(transport))
            with TestClient(application.app) as client:
                response = client.post(
                    "/api/jobs",
                    headers={"X-PastPort-Edit": "1"},
                    data={
                        "options": json.dumps(
                            {
                                "workflow": "environment_build",
                                "title": "Browser fixture",
                                "authorize_model": True,
                            }
                        )
                    },
                    files=[
                        ("document", ("matched.pdf", pdf.read_bytes(), "application/pdf")),
                        ("tour", ("index.html", tour.read_bytes(), "text/html")),
                    ],
                )
                self.assertEqual(response.status_code, 202, response.text)
                job = response.json()
                for _ in range(400):
                    current = client.get("/api/jobs").json()[0]
                    if current["status"] != "running":
                        break
                    time.sleep(0.05)
                self.assertIn(current["status"], ("completed", "completed_with_gaps"), current)
                base = f"/projects/{job['project_id']}/runs/{job['job_id']}/"
                redirect = client.get(base, follow_redirects=False)
                self.assertEqual(redirect.status_code, 307, redirect.text)
                url = redirect.headers["location"]
                with httpx.Client(trust_env=False) as browser:
                    self.assertEqual(browser.get(url).status_code, 200)
                    data = browser.get(url + "api/data").json()
                    self.assertIn("Browser fixture", browser.get(url).text)
                    self.assertTrue(data)
                    content = browser.get(url + "api/vr-content?object_id=27").json()
                    edit = {
                        "object_id": 27,
                        "version": content["version"],
                        "content": "Human text survives restart",
                        "editor": "fixture-reviewer",
                    }
                    self.assertEqual(
                        browser.post(
                            url + "api/vr-content", json=edit, headers={"Origin": url.rstrip("/")}
                        ).status_code,
                        200,
                    )
                    self.assertEqual(
                        browser.post(
                            url + "api/vr-content", json=edit, headers={"Origin": url.rstrip("/")}
                        ).status_code,
                        409,
                    )
                    vr = client.get(base + "vr/", follow_redirects=False).headers["location"]
                    self.assertIn("vr_trial/index.html", vr)
                    self.assertEqual(browser.get(vr).status_code, 200)
                    # A mutable file in the output must never become executed server code.
                    output = (
                        application.jobs.root
                        / "projects"
                        / job["project_id"]
                        / "runs"
                        / job["job_id"]
                        / "result"
                    )
                    (output / "review_server.py").write_text(
                        'raise RuntimeError("untrusted output code")'
                    )
                    self.assertIsNotNone(client.portal)
                    assert client.portal is not None
                    client.portal.call(application.previews.close)
                    url = client.get(base, follow_redirects=False).headers["location"]
                    self.assertEqual(
                        browser.get(url + "api/vr-content?object_id=27").json()["content"],
                        "Human text survives restart",
                    )
                    calls = len(transport.calls)
                    repeated = client.post(
                        "/api/jobs",
                        headers={"X-PastPort-Edit": "1"},
                        data={
                            "options": json.dumps(
                                {
                                    "workflow": "environment_build",
                                    "title": "Browser fixture",
                                    "project_id": job["project_id"],
                                    "authorize_model": True,
                                }
                            )
                        },
                        files=[
                            ("document", ("matched.pdf", pdf.read_bytes(), "application/pdf")),
                            ("tour", ("index.html", tour.read_bytes(), "text/html")),
                        ],
                    )
                    self.assertEqual(repeated.status_code, 202, repeated.text)
                    second = repeated.json()
                    for _ in range(100):
                        if client.get("/api/jobs").json()[0]["status"] != "running":
                            break
                        time.sleep(0.05)
                    second_url = client.get(
                        f"/projects/{job['project_id']}/runs/{second['job_id']}/",
                        follow_redirects=False,
                    ).headers["location"]
                    self.assertEqual(second_url, url)
                    self.assertEqual(len(transport.calls), calls)
                    self.assertEqual(
                        browser.get(second_url + "api/vr-content?object_id=27").json()["content"],
                        "Human text survives restart",
                    )
            with httpx.Client(trust_env=False, timeout=1) as browser:
                with self.assertRaises(httpx.ConnectError):
                    browser.get(url)

    def test_4k_panorama_uses_bounded_preview_and_original_pixel_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "large-panorama", 1)
            match = re.search(
                r'<script id="tour-data" type="application/json">(.*?)</script>',
                tour.read_text(),
                re.S,
            )
            assert match is not None
            data = json.loads(match.group(1))
            buffer = io.BytesIO()
            with Image.new("RGB", (4096, 2048), "navy") as image:
                image.save(buffer, "JPEG")
            data["scenes"][0]["panorama"] = {
                "data": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode(),
                "width": 4096,
                "height": 2048,
            }
            tour.write_text(
                '<script id="tour-data" type="application/json">' + json.dumps(data) + "</script>"
            )
            binary = shutil.which("pdftoppm")
            assert binary is not None
            transport = EnvironmentFixtureTransport()
            workspace = root / "workspace"
            EnvironmentBuildWorkflow(Path(binary), transport).run(
                pdf,
                tour,
                SubscriptionGrant(
                    project_id="fixture",
                    grant_ref="fixture:4k",
                    max_calls=20,
                    max_recorded_tokens=10000,
                ),
                workspace,
                "large",
            )
            run = workspace / "runs/large"
            with Image.open(run / "overview-1.jpg") as image:
                self.assertEqual(image.size, (2048, 1024))
            report = json.loads((run / "result/vr_trial/trial_report.json").read_text())
            self.assertEqual(report["located"][0]["pixel_center"], [int(4096 * 0.3), 1024])
            self.assertEqual(
                report["located"][0]["panorama_sha256"],
                hashlib.sha256(buffer.getvalue()).hexdigest(),
            )

    def test_unmapped_historical_parent_is_not_a_fabricated_catalog_identity(self) -> None:
        transport = EnvironmentFixtureTransport()
        from pastport_pdf_vr.application.environment_build import PDFPageInput

        request = PDFBatchInput(
            pages=(PDFPageInput(page=1, native_text="Actual native quote."),), known_objects=()
        )
        response = transport.execute(
            ExecutionInput(
                project_id="fixture",
                grant_ref="fixture:grant",
                model_id="fixture-model",
                kind="environment_generation",
                prompt_version="v1",
                policy_version="v1",
                instructions="Fixture",
                payload_json=request.model_dump_json(),
                output_schema_json="{}",
            ),
            120,
        )
        original = MatchedBatch.model_validate_json(response.payload_json).objects[0]
        payload = original.model_dump_json()
        data = json.loads(payload)
        data["historical_relation"] = "fixed_part_of"
        self.assertIsNone(MatchedObject.model_validate_json(json.dumps(data)).whole_number)
        data["whole_number"] = 99
        data["historical_relation"] = None
        with self.assertRaises(ValueError):
            MatchedObject.model_validate_json(json.dumps(data))

    def test_coordinate_arrays_use_provider_compatible_homogeneous_items(self) -> None:
        schema = json.loads(
            StrictOutputSchema.convert(json.dumps(MatchedBatch.model_json_schema()))
        )
        box = schema["$defs"]["PageCrop"]["properties"]["box"]
        self.assertNotIn("prefixItems", box)
        self.assertEqual(box["items"]["type"], "number")
        self.assertEqual((box["minItems"], box["maxItems"]), (4, 4))
        with self.assertRaises(ValueError):
            StrictOutputSchema.convert(
                json.dumps(
                    {"type": "array", "prefixItems": [{"type": "string"}, {"type": "number"}]}
                )
            )

    def test_linked_pdf_inspects_detail_pages_and_preserves_photo_selections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "linked-source", 1)
            photo = root / "photo.jpg"
            with Image.new("RGB", (400, 200), "navy") as image:
                image.save(photo)
            canvas = Canvas(str(pdf), pagesize=(400, 300))
            canvas.bookmarkPage("overview")
            canvas.drawString(20, 280, "Photographic overview")
            canvas.drawImage(str(photo), 20, 100, width=300, height=150)
            canvas.linkRect("", "detail", (40, 120, 80, 160), thickness=0)
            canvas.linkRect("", "detail", (330, 100, 390, 200), thickness=0)
            canvas.showPage()
            canvas.bookmarkPage("detail")
            canvas.drawString(20, 280, "27 -> K90 | Full evidence")
            canvas.drawString(20, 250, "The documented fixture has a fixed recess.")
            canvas.drawImage(str(photo), 20, 50, width=100, height=50)
            canvas.linkRect("", "overview", (20, 50, 120, 100), thickness=0)
            canvas.save()
            transport = EnvironmentFixtureTransport()
            binary = shutil.which("pdftoppm")
            assert binary is not None
            workspace = root / "workspace"
            EnvironmentBuildWorkflow(Path(binary), transport).run(
                pdf,
                tour,
                SubscriptionGrant(
                    project_id="fixture",
                    grant_ref="fixture:indexed",
                    max_calls=20,
                    max_recorded_tokens=10000,
                ),
                workspace,
                "indexed",
            )
            request = PDFBatchInput.model_validate_json(transport.calls[0].payload_json)
            self.assertEqual([p.page for p in request.pages], [2])
            self.assertEqual(request.expected_entries[0].history_key, "K90")
            self.assertIn('"K90"', (workspace / "runs/indexed/result/index.html").read_text())
            index = json.loads((workspace / "runs/indexed/matched-pdf-index.json").read_text())
            self.assertEqual(len(index["entries"][0]["modern_images"]), 1)
            crop = index["entries"][0]["modern_images"][0]
            self.assertEqual(crop["page"], 1)
            self.assertEqual(crop["box"], [0.1, 140 / 300, 0.2, 0.6])

    def test_settled_inspection_validation_recovery_reuses_the_model_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "recover-source", 1)
            binary = shutil.which("pdftoppm")
            assert binary is not None
            transport = EnvironmentFixtureTransport()
            workflow = EnvironmentBuildWorkflow(Path(binary), transport)
            grant = SubscriptionGrant(
                project_id="fixture",
                grant_ref="fixture:recovery",
                max_calls=20,
                max_recorded_tokens=10000,
            )
            original = MatchedBatch.model_validate_json
            once = True

            def legacy_validation(data: str, **kwargs: object) -> MatchedBatch:
                nonlocal once
                if once:
                    once = False
                    raise ValidationError.from_exception_data(
                        "Legacy boundary",
                        [
                            {
                                "type": "value_error",
                                "loc": ("objects", 0),
                                "input": None,
                                "ctx": {"error": ValueError("Legacy validation repaired")},
                            }
                        ],
                    )
                return original(data)

            with patch.object(MatchedBatch, "model_validate_json", side_effect=legacy_validation):
                with self.assertRaises(ValidationError):
                    workflow.run(pdf, tour, grant, root / "workspace", "recover")
            self.assertEqual(len(transport.calls), 1)
            workflow.run(pdf, tour, grant, root / "workspace", "recover", resume_inspection=True)
            with sqlite3.connect(root / "workspace/codex-executions.sqlite3") as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM executions").fetchone()[0],
                    len(transport.calls),
                )
            with sqlite3.connect(root / "workspace/stages.sqlite3") as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM pipeline_recoveries").fetchone(), (1,)
                )
            first_calls = [r for r in transport.calls if "pages" in json.loads(r.payload_json)]
            self.assertEqual(len(first_calls), 1)

    def test_visual_pair_cost_guard_avoids_an_unaffordable_unreviewed_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "budget-view", 2)
            binary = shutil.which("pdftoppm")
            assert binary is not None
            transport = EnvironmentFixtureTransport()
            summary = EnvironmentBuildWorkflow(Path(binary), transport).run(
                pdf,
                tour,
                SubscriptionGrant(
                    project_id="fixture",
                    grant_ref="fixture:pair-budget",
                    max_calls=20,
                    max_recorded_tokens=100,
                ),
                root / "workspace",
                "budget",
            )
            self.assertEqual(len(transport.calls), 4)
            self.assertEqual(summary.anchor_count, 1)
            self.assertTrue(
                any(g.startswith("localization_budget_exhausted:") for g in summary.gaps)
            )

    def test_production_runner_selects_sdk_environment_command(self) -> None:
        class Process:
            pid = 99999999
            returncode = 0

            async def wait(self) -> int:
                return 0

        async def exercise() -> None:
            with patch("asyncio.create_subprocess_exec", return_value=Process()) as create:
                code = await SubprocessBuildRunner().run(
                    Path("a.pdf"),
                    Path("tour.html"),
                    Path("grant.json"),
                    Path("workspace"),
                    "run",
                    StudioOptions(
                        workflow="environment_build", title="Title", authorize_model=True
                    ),
                )
                self.assertEqual(code, 0)
                self.assertIn("environment-build", create.call_args.args)
                self.assertNotIn("build", create.call_args.args)

        asyncio.run(exercise())
