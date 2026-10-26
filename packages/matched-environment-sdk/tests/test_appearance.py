"""Museum verifies appearance identity and bytes without a stylization dependency."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pastport_matched_environment.application.appearance import current_style
from pastport_matched_environment.domain.appearance import (
    SplatBakeStats,
    Style3DVariant,
    StyleCamera,
)
from pastport_matched_environment.domain.scene3d import MarbleScene, Point3D


class AppearanceManifestTests(unittest.TestCase):
    def test_foreign_binding_and_modified_bytes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "scene3d"
            folder.mkdir()
            checksum = hashlib.sha256(b"synthetic-offline-asset").hexdigest()
            for name in ("scene.spz", "scene-styled.spz", "style-panorama.png"):
                (folder / name).write_bytes(b"synthetic-offline-asset")
            scene = MarbleScene(
                scene_id="scene-1",
                binding="a" * 64,
                splat_sha256=checksum,
                collider_sha256=checksum,
                panorama_sha256=checksum,
                metric_scale_factor=1.0,
                ground_plane_offset=0.0,
            )
            (folder / "attachment.json").write_text(
                json.dumps(
                    {
                        "binding": "a" * 64,
                        "scene": scene.model_dump(),
                    }
                )
            )
            variant = Style3DVariant(
                scene_binding="a" * 64,
                world_id="scene-1",
                source_scene_id="scene-1",
                base_splat="scene.spz",
                base_splat_sha256=checksum,
                splat_sha256=checksum,
                panorama_sha256=checksum,
                source_panorama_sha256=checksum,
                style_reference_sha256=checksum,
                provenance_ref="synthetic-offline-test",
                camera=StyleCamera(origin=Point3D(x=0.0, y=0.0, z=0.0)),
                alignment_kind="automatic_estimate",
                stats=SplatBakeStats(splat_count=1, projected_count=1, occluded_palette_count=0),
            )
            manifest = folder / "style-variant.json"
            manifest.write_text(variant.model_dump_json())
            self.assertEqual(current_style(root), variant)
            manifest.write_text(
                variant.model_copy(update={"scene_binding": "b" * 64}).model_dump_json()
            )
            with self.assertRaisesRegex(ValueError, "another scene"):
                current_style(root)
            manifest.write_text(variant.model_dump_json())
            (folder / "scene-styled.spz").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                current_style(root)
