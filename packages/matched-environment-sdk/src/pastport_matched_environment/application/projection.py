"""Invert stored image transforms before interpreting model pixels as VR angles."""

from __future__ import annotations

import math

from pastport_matched_environment.domain.geometry import (
    CropTransform,
    EquirectangularTransform,
    ImageTransform,
    PerspectiveTransform,
    PixelPoint,
    SphericalPoint,
)

Vector = tuple[float, float, float]


def wrap_yaw(yaw: float) -> float:
    return (yaw + 180.0) % 360.0 - 180.0


def camera_basis(transform: PerspectiveTransform) -> tuple[Vector, Vector, Vector]:
    yaw, pitch, roll = map(
        math.radians,
        (
            transform.center_yaw,
            transform.center_pitch,
            transform.roll,
        ),
    )
    forward = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
    right = (math.cos(yaw), 0.0, -math.sin(yaw))
    up = (-math.sin(yaw) * math.sin(pitch), math.cos(pitch), -math.cos(yaw) * math.sin(pitch))
    # Positive roll rotates the camera's right basis toward its up basis.
    rotated_right = tuple(right[i] * math.cos(roll) + up[i] * math.sin(roll) for i in range(3))
    rotated_up = tuple(up[i] * math.cos(roll) - right[i] * math.sin(roll) for i in range(3))
    return (
        forward,
        (rotated_right[0], rotated_right[1], rotated_right[2]),
        (
            rotated_up[0],
            rotated_up[1],
            rotated_up[2],
        ),
    )


def pixel_to_sphere(point: PixelPoint, transform: ImageTransform) -> SphericalPoint:
    if point.x > transform.image_width or point.y > transform.image_height:
        raise ValueError("Selected point lies outside its matching image")
    u, v = point.x / transform.image_width, point.y / transform.image_height
    if isinstance(transform, EquirectangularTransform):
        return SphericalPoint(yaw=wrap_yaw(360 * u - 180), pitch=90 - 180 * v)
    if isinstance(transform, CropTransform):
        source_u = (transform.source_x + u * transform.crop_width) % transform.source_width
        source_v = transform.source_y + v * transform.crop_height
        return SphericalPoint(
            yaw=wrap_yaw(360 * source_u / transform.source_width - 180),
            pitch=90 - 180 * source_v / transform.source_height,
        )
    forward, right, up = camera_basis(transform)
    tangent = math.tan(math.radians(transform.horizontal_fov) / 2)
    x = (2 * u - 1) * tangent
    y = (1 - 2 * v) * tangent * transform.image_height / transform.image_width
    ray = tuple(forward[i] + x * right[i] + y * up[i] for i in range(3))
    length = math.sqrt(sum(component**2 for component in ray))
    return SphericalPoint(
        yaw=wrap_yaw(math.degrees(math.atan2(ray[0], ray[2]))),
        pitch=math.degrees(math.asin(max(-1.0, min(1.0, ray[1] / length)))),
    )


def sphere_to_pixel(point: SphericalPoint, transform: ImageTransform) -> PixelPoint | None:
    u, v = (point.yaw + 180) / 360, (90 - point.pitch) / 180
    if isinstance(transform, EquirectangularTransform):
        return PixelPoint(x=u * transform.image_width, y=v * transform.image_height)
    if isinstance(transform, CropTransform):
        x = (u * transform.source_width - transform.source_x) % transform.source_width
        y = v * transform.source_height - transform.source_y
        if x > transform.crop_width or y < 0 or y > transform.crop_height:
            return None
        return PixelPoint(
            x=x / transform.crop_width * transform.image_width,
            y=y / transform.crop_height * transform.image_height,
        )
    yaw, pitch = math.radians(point.yaw), math.radians(point.pitch)
    ray = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
    forward, right, up = camera_basis(transform)
    z = sum(ray[i] * forward[i] for i in range(3))
    if z <= 1e-12:
        return None
    tangent = math.tan(math.radians(transform.horizontal_fov) / 2)
    x = (sum(ray[i] * right[i] for i in range(3)) / z / tangent + 1) / 2
    y = (
        1
        - sum(ray[i] * up[i] for i in range(3))
        / z
        / tangent
        * transform.image_width
        / transform.image_height
    ) / 2
    if not (-1e-10 <= x <= 1 + 1e-10 and -1e-10 <= y <= 1 + 1e-10):
        return None
    return PixelPoint(
        x=max(0.0, min(1.0, x)) * transform.image_width,
        y=max(0.0, min(1.0, y)) * transform.image_height,
    )


def angular_distance(first: SphericalPoint, second: SphericalPoint) -> float:
    p1, p2 = math.radians(first.pitch), math.radians(second.pitch)
    cosine = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(
        math.radians(wrap_yaw(first.yaw - second.yaw))
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
