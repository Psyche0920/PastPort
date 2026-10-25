"""Versioned Marble input and metric-space manual anchor contracts."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.models import DomainModel


class MarbleScene(DomainModel):
    schema_version: Literal[1] = 1
    kind: Literal["marble_3d"] = "marble_3d"
    scene_id: str
    binding: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    splat: Literal["scene.spz"] = "scene.spz"
    collider: Literal["collider.glb"] = "collider.glb"
    panorama: Literal["panorama.jpg"] = "panorama.jpg"
    splat_sha256: str
    collider_sha256: str
    panorama_sha256: str
    metric_scale_factor: Annotated[float, Field(gt=0, le=10000, allow_inf_nan=False)]
    ground_plane_offset: Annotated[float, Field(ge=-10000, le=10000, allow_inf_nan=False)]
    coordinate_frame: Literal["three_metric_y_up"] = "three_metric_y_up"
    acceptance: Literal["pending_manual_review"] = "pending_manual_review"


class Point3D(DomainModel):
    x: Annotated[float, Field(ge=-10000, le=10000, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=-10000, le=10000, allow_inf_nan=False)]
    z: Annotated[float, Field(ge=-10000, le=10000, allow_inf_nan=False)]


class AnchorEdit(DomainModel):
    operation_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")]
    scene_binding: str
    object_id: Annotated[int, Field(ge=1)]
    historical_id: str
    expected_version: Annotated[int, Field(ge=0)]
    point: Point3D | None
    editor: Annotated[str, Field(min_length=1, max_length=100)]
    identity_basis: Annotated[str, Field(min_length=1, max_length=1000)]
    relation_basis: Annotated[str, Field(max_length=1000)] = ""


class AlignmentEdit(DomainModel):
    scene_binding: str
    expected_version: Annotated[int, Field(ge=0)]
    confirmed: bool
    origin: Point3D
    yaw_degrees: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    pitch_degrees: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    roll_degrees: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    editor: Annotated[str, Field(min_length=1, max_length=100)]
    basis: Annotated[str, Field(min_length=1, max_length=1000)]


class Scene3DRecord(DomainModel):
    run_id: str
    title: str
    mode: str
    status: str
    message: str
    url: str = ""
    review_url: str = ""
    splat_url: str = ""
    collider_url: str = ""
    manifest_url: str = ""
    package_url: str = ""
    resume: str = ""


class SceneRenderVariant(DomainModel):
    scene_binding: str
    world_id: str
    splat: Literal["scene-full.spz"] = "scene-full.spz"
    splat_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    tier: Literal["full_res"] = "full_res"
