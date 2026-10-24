"""Render matching images using the same camera convention as coordinate inversion."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from pastport_pdf_vr.application.projection import camera_basis
from pastport_pdf_vr.domain.geometry import (
    CropTransform,
    EquirectangularTransform,
    ImageTransform,
)


class ProjectionError(ValueError):
    """A source panorama or derived image violates the projection contract."""


class PanoramaProjector:
    def render(
        self, source_path: Path, transform: ImageTransform, max_output_bytes: int = 4 * 1024 * 1024
    ) -> bytes:
        if (
            not 1 <= max_output_bytes <= 4 * 1024 * 1024
            or source_path.stat().st_size > 16 * 1024 * 1024
        ):
            raise ProjectionError("Panorama encoded size or output bound is invalid")
        try:
            with Image.open(source_path) as source:
                if source.size != (transform.source_width, transform.source_height):
                    raise ProjectionError("Transform dimensions do not match the source panorama")
                with source.convert("RGB") as rgb:
                    pixels = np.asarray(rgb, dtype=np.uint8)
            # Pixel centers are sampled; model coordinates use the surrounding image edges.
            sampled = np.empty((transform.image_height, transform.image_width, 3), dtype=np.uint8)
            for row in range(0, transform.image_height, 128):
                stop = min(row + 128, transform.image_height)
                u, v = np.meshgrid(
                    (np.arange(transform.image_width) + 0.5) / transform.image_width,
                    (np.arange(row, stop) + 0.5) / transform.image_height,
                )
                source_u, source_v = self._source_uv(u, v, transform)
                sampled[row:stop] = self._bilinear(pixels, source_u, source_v)
            output = io.BytesIO()
            with Image.fromarray(sampled) as rendered:
                rendered.save(output, format="JPEG", quality=88)
            content = output.getvalue()
        except (OSError, Image.DecompressionBombError) as error:
            raise ProjectionError("Panorama image could not be decoded or projected") from error
        if len(content) > max_output_bytes:
            raise ProjectionError("Derived matching image exceeds its encoded byte limit")
        return content

    @staticmethod
    def _source_uv(
        u: NDArray[np.float64], v: NDArray[np.float64], transform: ImageTransform
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        if isinstance(transform, EquirectangularTransform):
            return u, v
        if isinstance(transform, CropTransform):
            return ((transform.source_x + u * transform.crop_width) / transform.source_width) % 1, (
                transform.source_y + v * transform.crop_height
            ) / transform.source_height
        forward, right, up = camera_basis(transform)
        tangent = np.tan(np.deg2rad(transform.horizontal_fov) / 2)
        x = (2 * u - 1) * tangent
        y = (1 - 2 * v) * tangent * transform.image_height / transform.image_width
        rx = forward[0] + x * right[0] + y * up[0]
        ry = forward[1] + x * right[1] + y * up[1]
        rz = forward[2] + x * right[2] + y * up[2]
        length = np.sqrt(rx * rx + ry * ry + rz * rz)
        return ((np.arctan2(rx, rz) / (2 * np.pi)) + 0.5) % 1, (
            0.5 - np.arcsin(np.clip(ry / length, -1, 1)) / np.pi
        )

    @staticmethod
    def _bilinear(
        pixels: NDArray[np.uint8], u: NDArray[np.float64], v: NDArray[np.float64]
    ) -> NDArray[np.uint8]:
        height, width = pixels.shape[:2]
        x = u * width - 0.5
        y = np.clip(v * height - 0.5, 0, height - 1)
        floor_x, floor_y = np.floor(x), np.floor(y)
        x0, y0 = floor_x.astype(np.int64) % width, floor_y.astype(np.int64)
        x1, y1 = (x0 + 1) % width, np.minimum(y0 + 1, height - 1)
        wx, wy = (x - floor_x)[..., None], (y - floor_y)[..., None]
        result = (1 - wy) * ((1 - wx) * pixels[y0, x0] + wx * pixels[y0, x1]) + wy * (
            (1 - wx) * pixels[y1, x0] + wx * pixels[y1, x1]
        )
        return np.asarray(np.clip(np.rint(result), 0, 255), dtype=np.uint8)
