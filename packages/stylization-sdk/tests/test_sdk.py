"""Reject malformed cross-package input and preserve resume style authority."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pastport_stylization.api.stylization_studio import create_app
from pastport_stylization.application.animation_style import approved_animation_style
from pastport_stylization.sdk import StyleInput
from pydantic import ValidationError


class StylizationBoundaryTests(unittest.TestCase):
    def test_source_identity_and_viewpoint_count_are_validated(self) -> None:
        valid = StyleInput(
            kind="panorama",
            source="museum.zip",
            viewpoints=2,
            required_calls=12,
            source_sha256="a" * 64,
        )
        self.assertEqual(valid.viewpoints, 2)
        for field, value in (
            ("source_sha256", "unknown"),
            ("viewpoints", 0),
            ("required_calls", -1),
            ("source", ""),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                StyleInput.model_validate({**valid.model_dump(), field: value})
        with self.assertRaises(ValidationError):
            StyleInput.model_validate({**valid.model_dump(), "authorize": True})

    def test_packaged_style_is_hash_bound_and_resume_never_falls_back(self) -> None:
        style = approved_animation_style()
        self.assertIsNotNone(style.standard)
        self.assertTrue(style.reference.is_file())
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            (workspace / "run-binding.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "no reset or fallback"):
                approved_animation_style(workspace)

    def test_separate_portal_serves_its_assets_and_shared_css_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(Path(folder))) as client:
                for path in (
                    "/stylization",
                    "/stylization.js",
                    "/static/stylization.css",
                    "/static/studio.css",
                ):
                    with self.subTest(path=path):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 200)
                        self.assertGreater(len(response.content), 0)
                self.assertNotIn("Environment matching", client.get("/stylization").text)
