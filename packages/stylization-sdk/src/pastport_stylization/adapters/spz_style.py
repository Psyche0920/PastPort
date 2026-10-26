"""Bake a registered painted panorama into SPZ v2 DC appearance coefficients.

The legacy SPZ layout/color constants follow Niantic's public format specification.
No positions, scales, rotations, opacities or point counts are changed.
"""

from __future__ import annotations

import gzip
import math
import struct
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from pastport_stylization.domain.stylization3d import SplatBakeStats, StyleCamera

FloatArray = NDArray[np.float64]
ByteArray = NDArray[np.uint8]


class SpzAppearanceError(ValueError):
    """Reject unsupported data before producing a misleading asset."""


def image_rgb(path: Path) -> ByteArray:
    with Image.open(path) as image:
        if image.width != image.height * 2 or image.width > 16384:
            raise SpzAppearanceError("Expected a bounded full 2:1 panorama")
        return np.asarray(image.convert("RGB"), dtype=np.uint8).copy()


def camera_rotation(camera: StyleCamera) -> FloatArray:
    """Match Three.js YXZ Euler order used by the existing 3D viewer."""
    x, y, z = map(math.radians, (camera.pitch_degrees, camera.yaw_degrees, camera.roll_degrees))
    cx, sx, cy, sy, cz, sz = (
        math.cos(x),
        math.sin(x),
        math.cos(y),
        math.sin(y),
        math.cos(z),
        math.sin(z),
    )
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    return ry @ rx @ rz


class SpzAppearanceBaker:
    """CPU vectorized, one-pass appearance conversion without provider calls."""

    def bake(
        self,
        source: Path,
        target: Path,
        original: Path,
        painted: Path,
        camera: StyleCamera,
        scale: float,
        ground: float,
        strength: float,
    ) -> SplatBakeStats:
        if source.stat().st_size > 256 * 1024**2:
            raise SpzAppearanceError("Compressed SPZ exceeds 256 MiB")
        with gzip.open(source, "rb") as stream:
            raw = bytearray(stream.read(256 * 1024**2 + 1))
        if len(raw) < 16 or len(raw) > 256 * 1024**2:
            raise SpzAppearanceError("Invalid or oversized decompressed SPZ")
        magic, version, count, degree, bits, flags, reserved = struct.unpack_from("<III4B", raw)
        if (
            magic != 0x5053474E
            or version != 2
            or degree != 0
            or flags & ~1
            or reserved
            or not 1 <= count <= 3_000_000
            or not 1 <= bits <= 24
        ):
            raise SpzAppearanceError("Only bounded SPZ v2, degree-zero Marble assets are supported")
        if len(raw) != 16 + count * 19:
            raise SpzAppearanceError("SPZ attribute sizes do not match its header")
        positions = np.frombuffer(raw, np.uint8, count=count * 9, offset=16).reshape(count, 3, 3)
        integers = (
            positions[:, :, 0].astype(np.int32)
            | positions[:, :, 1].astype(np.int32) << 8
            | positions[:, :, 2].astype(np.int32) << 16
        )
        integers = (integers ^ 0x800000) - 0x800000
        world = integers.astype(np.float64) / (1 << bits) * scale
        world[:, 1:] *= -1  # Same X half-turn as the existing viewer's asset group.
        world[:, 1] += ground
        world -= np.array([camera.origin.x, camera.origin.y, camera.origin.z])
        local = world @ camera_rotation(camera)
        distances = np.linalg.norm(local, axis=1)
        safe = np.maximum(distances, 1e-9)
        u = (0.5 + np.arctan2(local[:, 0], -local[:, 2]) / (2 * np.pi)) % 1
        v = np.clip(0.5 - np.arcsin(np.clip(local[:, 1] / safe, -1, 1)) / np.pi, 0, 1)
        source_rgb, style_rgb = image_rgb(original), image_rgb(painted)
        if source_rgb.shape != style_rgb.shape:
            raise SpzAppearanceError("Painted panorama must retain native source dimensions")
        height, width = style_rgb.shape[:2]
        px = np.minimum((u * width).astype(np.int64), width - 1)
        py = np.minimum((v * height).astype(np.int64), height - 1)
        # A conservative angular z-buffer prevents projecting foreground patterns on hidden backs.
        bx = np.minimum((u * 1024).astype(np.int64), 1023)
        by = np.minimum((v * 512).astype(np.int64), 511)
        bins = by * 1024 + bx
        depth = np.full(1024 * 512, np.inf)
        alpha = np.frombuffer(raw, np.uint8, count=count, offset=16 + count * 9)
        credible = (alpha >= 32) & (distances > 0.02)
        np.minimum.at(depth, bins[credible], distances[credible])
        near = depth[bins]
        visible = credible & (distances <= near + np.maximum(0.20, near * 0.08))
        offset = 16 + count * 10
        packed = np.frombuffer(raw, np.uint8, count=count * 3, offset=offset).reshape(count, 3)
        rgb = np.clip(
            (packed.astype(np.float64) / 255 - 0.5) / 0.15 * 0.28209479177387814 + 0.5, 0, 1
        )
        # Hidden surfaces get a source-paired palette, never an invented projected object texture.
        palette = self._palette(source_rgb, style_rgb)
        indexes = np.minimum((rgb * 15).astype(np.int64), 15)
        target_rgb = palette[indexes[:, 0] * 256 + indexes[:, 1] * 16 + indexes[:, 2]]
        target_rgb[visible] = style_rgb[py[visible], px[visible]].astype(np.float64) / 255
        result = rgb * (1 - strength) + target_rgb * strength
        encoded = ((result - 0.5) / 0.28209479177387814 * 0.15 + 0.5) * 255
        packed[:] = np.rint(np.clip(encoded, 0, 255)).astype(np.uint8)
        with target.open("xb") as file:
            with gzip.GzipFile(fileobj=file, mode="wb", compresslevel=6, mtime=0) as stream:
                stream.write(raw)
        projected = int(np.count_nonzero(visible))
        return SplatBakeStats(
            splat_count=count, projected_count=projected, occluded_palette_count=count - projected
        )

    @staticmethod
    def _palette(source: ByteArray, painted: ByteArray) -> FloatArray:
        original = source[::4, ::4].reshape(-1, 3).astype(np.int64) * 15 // 255
        target = painted[::4, ::4].reshape(-1, 3).astype(np.float64) / 255
        ids = original[:, 0] * 256 + original[:, 1] * 16 + original[:, 2]
        counts = np.bincount(ids, minlength=4096)
        colors = np.zeros((4096, 3), dtype=np.float64)
        for channel in range(3):
            colors[:, channel] = np.bincount(ids, weights=target[:, channel], minlength=4096)
        known = np.flatnonzero(counts)
        colors[known] /= counts[known, None]
        grid = np.array([(i // 256, i // 16 % 16, i % 16) for i in range(4096)])
        for index in np.flatnonzero(counts == 0):
            nearest = known[np.argmin(np.sum((grid[known] - grid[index]) ** 2, axis=1))]
            colors[index] = colors[nearest]
        return colors
