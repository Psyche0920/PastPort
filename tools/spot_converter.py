"""Spherical coordinates to normalized Spot(x, y) converter and angular distance metric.

Converts between 360 viewer (yaw, pitch) and PastPort Spot coordinates (x, y in [0, 10000]).
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class SphericalCoordinate:
    yaw: float    # -180.0 to +180.0 degrees (longitude)
    pitch: float  # -90.0 to +90.0 degrees (latitude)

    def to_spot(self) -> tuple[int, int]:
        """Convert (yaw, pitch) to PastPort normalized integer coordinates [0..10000]."""
        clamped_yaw = max(-180.0, min(180.0, self.yaw))
        clamped_pitch = max(-90.0, min(90.0, self.pitch))
        x = round(((clamped_yaw + 180.0) / 360.0) * 10000)
        y = round(((90.0 - clamped_pitch) / 180.0) * 10000)
        return max(0, min(10000, x)), max(0, min(10000, y))

    @classmethod
    def from_spot(cls, x: int, y: int) -> SphericalCoordinate:
        """Convert PastPort Spot [0..10000] back to (yaw, pitch) in degrees."""
        clamped_x = max(0, min(10000, x))
        clamped_y = max(0, min(10000, y))
        yaw = (clamped_x / 10000.0) * 360.0 - 180.0
        pitch = 90.0 - (clamped_y / 10000.0) * 180.0
        return cls(yaw=round(yaw, 2), pitch=round(pitch, 2))


def spherical_angular_distance(p1: SphericalCoordinate, p2: SphericalCoordinate) -> float:
    """Calculate great-circle angular distance in degrees between two points on a sphere."""
    lat1 = math.radians(p1.pitch)
    lat2 = math.radians(p2.pitch)
    delta_lon = math.radians(p2.yaw - p1.yaw)

    # Spherical law of cosines (numerically clamped to [-1, 1])
    cos_angle = math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(delta_lon)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def spot_angular_distance(spot1: tuple[int, int], spot2: tuple[int, int]) -> float:
    """Calculate great-circle angular distance in degrees between two PastPort Spot tuples (x, y)."""
    p1 = SphericalCoordinate.from_spot(spot1[0], spot1[1])
    p2 = SphericalCoordinate.from_spot(spot2[0], spot2[1])
    return spherical_angular_distance(p1, p2)


if __name__ == "__main__":
    # Smoke test
    center = SphericalCoordinate(yaw=0.0, pitch=0.0)
    sx, sy = center.to_spot()
    print(f"(0, 0) -> spot: ({sx}, {sy})")
    assert (sx, sy) == (5000, 5000)

    back = SphericalCoordinate.from_spot(sx, sy)
    assert (back.yaw, back.pitch) == (0.0, 0.0)

    offset = SphericalCoordinate(yaw=10.0, pitch=0.0)
    dist = spherical_angular_distance(center, offset)
    print(f"Angular distance: {dist:.2f}° (expected 10.00°)")
    assert round(dist, 2) == 10.00
    print("spot_converter smoke test passed.")
