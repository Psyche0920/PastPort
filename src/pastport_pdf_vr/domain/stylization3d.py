"""Source-bound 3D appearance baking; geometry and matching stay independent."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.animation import ExistingPanorama
from pastport_pdf_vr.domain.models import DomainModel, Sha256
from pastport_pdf_vr.domain.scene3d import Point3D


class StyleCamera(DomainModel):
    origin: Point3D
    yaw_degrees: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)
    pitch_degrees: float = Field(default=0, ge=-90, le=90, allow_inf_nan=False)
    roll_degrees: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)
    confirmed: bool = False
    version: int = Field(default=0, ge=0)
    editor: str = ""
    basis: str = ""


class Style3DRun(DomainModel):
    source_directory: str
    workspace: str
    panorama: ExistingPanorama
    strength: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1
    resume: bool = False


class SplatBakeStats(DomainModel):
    splat_count: int
    projected_count: int
    occluded_palette_count: int
    geometry_preserved: Literal[True] = True


class Style3DVariant(DomainModel):
    schema_version: Literal["pastport.style3d/1.0"] = "pastport.style3d/1.0"
    scene_binding: Sha256
    world_id: str
    source_scene_id: str
    base_splat: Literal["scene.spz", "scene-full.spz"]
    base_splat_sha256: Sha256
    splat: Literal["scene-styled.spz"] = "scene-styled.spz"
    splat_sha256: Sha256
    panorama: Literal["style-panorama.png"] = "style-panorama.png"
    panorama_sha256: Sha256
    source_panorama_sha256: Sha256
    style_reference_sha256: Sha256
    provenance_ref: str
    camera: StyleCamera
    alignment_kind: Literal["human_alignment", "automatic_estimate"]
    stats: SplatBakeStats
    new_model_calls: Literal[0] = 0
    geometry_repair: Literal["not_performed"] = "not_performed"
    acceptance: Literal["pending_user_acceptance"] = "pending_user_acceptance"


class Style3DDelivery(DomainModel):
    environment: str
    archive: str
    manifest: str
    source_scene_id: str
    acceptance: Literal["pending_user_acceptance"] = "pending_user_acceptance"
    new_model_calls: Literal[0] = 0
