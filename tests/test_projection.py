"""Geometry checks use known rays and actual synthetic pixels, not model answers."""

import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import ValidationError

from pastport_pdf_vr.adapters.projection import PanoramaProjector
from pastport_pdf_vr.application.projection import (
    angular_distance,
    pixel_to_sphere,
    sphere_to_pixel,
)
from pastport_pdf_vr.domain.geometry import (
    AnchorPosition,
    CropTransform,
    EquirectangularTransform,
    PerspectiveTransform,
    PixelPoint,
    SphericalPoint,
)


class ProjectionTests(unittest.TestCase):
    def test_known_equirectangular_axes_and_pole_rejection(self) -> None:
        transform = EquirectangularTransform(
            source_width=800, source_height=400, image_width=400, image_height=200
        )
        center = pixel_to_sphere(PixelPoint(x=200.0, y=100.0), transform)
        self.assertAlmostEqual(center.yaw, 0)
        self.assertAlmostEqual(center.pitch, 0)
        self.assertEqual(pixel_to_sphere(PixelPoint(x=400.0, y=100.0), transform).yaw, -180)
        pole = pixel_to_sphere(PixelPoint(x=100.0, y=0.0), transform)
        with self.assertRaises(ValidationError):
            AnchorPosition(yaw=pole.yaw, pitch=pole.pitch)

    def test_perspective_roundtrip_yaw_pitch_roll_and_seam(self) -> None:
        for yaw in (-179.0, 0.0, 65.0, 179.0):
            for pitch in (-40.0, 0.0, 60.0):
                for roll in (0.0, 90.0):
                    transform = PerspectiveTransform(
                        source_width=800,
                        source_height=400,
                        image_width=300,
                        image_height=200,
                        center_yaw=yaw,
                        center_pitch=pitch,
                        horizontal_fov=100.0,
                        roll=roll,
                    )
                    for x, y in ((150.0, 100.0), (0.0, 0.0), (299.0, 199.0), (40.0, 140.0)):
                        original = PixelPoint(x=x, y=y)
                        angles = pixel_to_sphere(original, transform)
                        restored = sphere_to_pixel(angles, transform)
                        self.assertIsNotNone(restored)
                        assert restored is not None
                        self.assertAlmostEqual(restored.x, x, places=8)
                        self.assertAlmostEqual(restored.y, y, places=8)
        transform = PerspectiveTransform(
            source_width=800,
            source_height=400,
            image_width=300,
            image_height=200,
            center_yaw=0.0,
            center_pitch=0.0,
            horizontal_fov=90.0,
        )
        self.assertIsNone(sphere_to_pixel(SphericalPoint(yaw=-180.0, pitch=0.0), transform))
        self.assertAlmostEqual(pixel_to_sphere(PixelPoint(x=300.0, y=100.0), transform).yaw, 45)

    def test_wrapped_crop_and_seam_distance(self) -> None:
        transform = CropTransform(
            source_width=800,
            source_height=400,
            image_width=200,
            image_height=100,
            source_x=760.0,
            source_y=100.0,
            crop_width=160.0,
            crop_height=80.0,
        )
        angles = pixel_to_sphere(PixelPoint(x=100.0, y=50.0), transform)
        self.assertAlmostEqual(angles.yaw, -162)
        restored = sphere_to_pixel(angles, transform)
        assert restored is not None
        self.assertAlmostEqual(restored.x, 100)
        self.assertAlmostEqual(
            angular_distance(
                SphericalPoint(yaw=179.9, pitch=0.0), SphericalPoint(yaw=-179.9, pitch=0.0)
            ),
            0.2,
        )

    def test_actual_perspective_sampling_uses_same_seam_and_pose(self) -> None:
        pixels = np.zeros((100, 200, 3), dtype=np.uint8)
        pixels[:, 90:110] = [240, 20, 20]  # yaw zero = center of the source image
        pixels[:, :10] = [20, 230, 20]
        pixels[:, -10:] = [20, 230, 20]  # both sides of the yaw seam are one green feature
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "panorama.png"
            Image.fromarray(pixels).save(source)
            for yaw, channel in ((0.0, 0), (179.9, 1)):
                transform = PerspectiveTransform(
                    source_width=200,
                    source_height=100,
                    image_width=81,
                    image_height=51,
                    center_yaw=yaw,
                    center_pitch=0.0,
                    horizontal_fov=60.0,
                )
                content = PanoramaProjector().render(source, transform)
                with Image.open(io.BytesIO(content)) as rendered:
                    center = rendered.getpixel((40, 25))
                    assert isinstance(center, tuple)
                    self.assertGreater(center[channel], 200)
                    self.assertLess(center[2], 50)
