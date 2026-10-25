"""Portable skill assembly checks use labeled inputs, not claims of new visual inference."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from pastport_pdf_vr.application.environment_agent import EnvironmentAgentPreparation
from pastport_pdf_vr.application.reference_environment import (
    CandidateBuilder,
    ImportFailure,
    RelationshipReview,
    digest,
    reference_assets,
    write_json,
)


def sample_inputs(root: Path, label: str, count: int) -> tuple[Path, Path]:
    pdf = root / "input.pdf"
    canvas = Canvas(str(pdf), pagesize=(400, 300))
    canvas.drawString(20, 250, f"The {label} has a fixed recess.")
    canvas.save()
    scenes: list[dict[str, object]] = []
    for n in range(count):
        buffer = io.BytesIO()
        with Image.new("RGB", (400, 200), (30 + n * 20, 40, 70)) as image:
            image.save(buffer, format="JPEG")
        scenes.append(
            {
                "id": f"{label}-view-{n}",
                "name": f"View {n}",
                "panorama": {
                    "data": "data:image/jpeg;base64,"
                    + base64.b64encode(buffer.getvalue()).decode(),
                    "width": 400,
                    "height": 200,
                    "source": "Explicit test counterpart; not real recognition",
                },
                "view": {"yaw": 0.0, "pitch": 0.0, "hfov": 90},
                "hotspots": [{"id": "old-answer", "type": "info", "yaw": 8, "pitch": 3}],
            }
        )
    tour = root / "tour.html"
    tour.write_text(
        '<script id="tour-data" type="application/json">'
        + json.dumps(
            {"schemaVersion": 4, "id": label, "firstSceneId": f"{label}-view-0", "scenes": scenes}
        )
        + "</script>"
    )
    return pdf, tour


def sample_evidence(root: Path, pdf: Path, tour: Path, number: int) -> tuple[Path, Path]:
    evidence = root / "evidence"
    media = evidence / "media"
    media.mkdir(parents=True)
    for name in ("input.pdf", "source.pdf"):
        shutil.copy2(pdf, evidence / name)
    # This exact quote is deliberately provided by a fixture counterpart.
    from pypdf import PdfReader

    with pdf.open("rb") as stream:
        quote = (PdfReader(stream).pages[0].extract_text() or "").strip()
    obj = {
        "number": number,
        "object_id": f"object:{number}",
        "name": "Fixture whole",
        "boundary": "Entire labeled fixture object",
        "history_id": f"subject:{number}",
        "history": "Fixture documented whole",
        "parent": "Fixture context",
        "page": 1,
        "image_page": None,
        "image_box": None,
        "explanation": "Explicit fixture only",
        "proxy": "Explicit fixture substitute",
        "limit": "Does not establish real-material recognition",
        "quote": quote,
        "observations": [],
    }
    write_json(evidence / "objects.json", {"title": "Fixture environment", "objects": [obj]})
    write_json(evidence / "inputs.json", {"input_page_count": 1, "photos": []})
    write_json(
        evidence / "quote-regions.json",
        [{"number": number, "page": 1, "normalized_text": quote, "start": 0, "end": len(quote)}],
    )
    with Image.new("RGB", (50, 50), "white") as image:
        image.save(media / f"history-{number:02d}.png")
    data = json.loads(tour.read_text().split(">", 1)[1].split("</script>")[0])
    positions = []
    for scene in data["scenes"]:
        raw = base64.b64decode(scene["panorama"]["data"].split(",", 1)[1])
        positions.append(
            {
                "object_number": number,
                "source_scene_id": scene["id"],
                "panorama_sha256": hashlib.sha256(raw).hexdigest(),
                "pixel_center": [200, 100],
                "basis": "Explicit fixture measurement, not a copied demo answer",
            }
        )
    locations = root / "locations.json"
    write_json(locations, {"input_html_sha256": digest(tour), "locations": positions})
    return evidence, locations


class EnvironmentAgentTests(unittest.TestCase):
    def test_different_pdfs_viewpoint_counts_and_object_numbers(self) -> None:
        binary = shutil.which("pdftoppm")
        self.assertIsNotNone(binary)
        for label, count, number in (("courtyard", 1, 5), ("museum", 3, 121)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                pdf, tour = sample_inputs(root, label, count)
                prepared = EnvironmentAgentPreparation(Path(str(binary))).prepare(
                    pdf, tour, root / "prepared"
                )
                self.assertEqual(prepared.viewpoint_count, count)
                self.assertEqual(prepared.page_count, 1)
                evidence, locations = sample_evidence(root, pdf, tour, number)
                result = root / "result"
                CandidateBuilder(reference_assets(), evidence, pdf, tour, locations, result).build()
                report = json.loads((result / "vr_trial/trial_report.json").read_text())
                self.assertEqual(report["hotspot_count"], count)
                self.assertEqual(report["viewpoint_count"], count)
                self.assertTrue(all(p["object_id"] == number for p in report["located"]))
                self.assertNotIn("old-answer", (result / "vr_trial/index.html").read_text())
                self.assertNotIn("Murat", (result / "vr_trial/index.html").read_text())
                with sqlite3.connect(result / "pastport_matching.sqlite3") as db:
                    self.assertEqual(
                        db.execute("SELECT id FROM modern_objects").fetchone()[0], number
                    )
                with self.assertRaises(ImportFailure):
                    CandidateBuilder(
                        reference_assets(), evidence, pdf, tour, locations, result
                    ).build()

    def test_changed_input_rejects_old_measurements_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "first", 1)
            evidence, locations = sample_evidence(root, pdf, tour, 77)
            tour.write_text(tour.read_text() + "\n<!-- changed import -->")
            with self.assertRaisesRegex(ImportFailure, "different VR import"):
                CandidateBuilder(
                    reference_assets(), evidence, pdf, tour, locations, root / "result"
                ).build()
            self.assertFalse((root / "result").exists())

    def test_relative_panorama_files_and_untrusted_basis_are_handled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "relative", 1)
            payload = json.loads(tour.read_text().split(">", 1)[1].split("</script>")[0])
            panorama = payload["scenes"][0]["panorama"]
            raw = base64.b64decode(panorama["data"].split(",", 1)[1])
            (root / "panorama.jpg").write_bytes(raw)
            evidence, locations = sample_evidence(root, pdf, tour, 306)
            panorama["data"] = "panorama.jpg"
            panorama.pop("width")
            panorama.pop("height")
            tour.write_text(
                '<script id="tour-data" type="application/json">'
                + json.dumps(payload)
                + "</script>"
            )
            measurements = json.loads(locations.read_text())
            measurements["input_html_sha256"] = digest(tour)
            measurements["locations"][0]["basis"] = "<script>untrusted()</script>"
            write_json(locations, measurements)
            result = root / "result"
            CandidateBuilder(reference_assets(), evidence, pdf, tour, locations, result).build()
            comparison = (result / "vr_trial/comparison.html").read_text()
            self.assertIn("&lt;script&gt;", comparison)
            self.assertNotIn("<script>untrusted()", comparison)

    def test_self_consistent_fabricated_quote_is_not_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, tour = sample_inputs(root, "quoted", 1)
            evidence, locations = sample_evidence(root, pdf, tour, 66)
            objects = json.loads((evidence / "objects.json").read_text())
            invented = "This sentence does not occur in the PDF."
            objects["objects"][0]["quote"] = invented
            write_json(evidence / "objects.json", objects)
            write_json(
                evidence / "quote-regions.json",
                [
                    {
                        "number": 66,
                        "page": 1,
                        "normalized_text": invented,
                        "start": 0,
                        "end": len(invented),
                    }
                ],
            )
            with self.assertRaisesRegex(ImportFailure, "not present on source page"):
                CandidateBuilder(
                    reference_assets(), evidence, pdf, tour, locations, root / "result"
                ).build()

    def test_relation_rule_does_not_depend_on_site_or_object_names(self) -> None:
        for a, b in ((1, 2), (405, 999)):
            from pastport_pdf_vr.application.reference_environment import Record

            relation: Record = {
                "whole_object_number": a,
                "part_object_number": b,
                "historical_relation": "fixed_part_of",
                "modern_relation": "unrelated",
                "verdict": "verified",
                "reason": "A separate object is not a fixed part of the whole",
            }
            with self.assertRaises(ImportFailure):
                RelationshipReview.parse(relation)
            relation["modern_relation"] = "within_whole"
            self.assertEqual(RelationshipReview.parse(relation).verdict, "verified")
