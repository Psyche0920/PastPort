"""Stylization-owned commands and delivery records; Museum owns appearance manifests."""

from typing import Annotated, Literal

from pastport_matched_environment.domain.animation import ExistingPanorama
from pastport_matched_environment.domain.appearance import (
    SplatBakeStats as SplatBakeStats,
)
from pastport_matched_environment.domain.appearance import (
    Style3DVariant as Style3DVariant,
)
from pastport_matched_environment.domain.appearance import (
    StyleCamera as StyleCamera,
)
from pastport_matched_environment.domain.models import DomainModel
from pydantic import Field


class Style3DRun(DomainModel):
    source_directory: str
    workspace: str
    panorama: ExistingPanorama
    strength: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1
    resume: bool = False
    render_mode: Literal["gaussian", "projective_surface"] = "gaussian"


class Style3DDelivery(DomainModel):
    environment: str
    archive: str
    manifest: str
    source_scene_id: str
    acceptance: Literal["pending_user_acceptance"] = "pending_user_acceptance"
    new_model_calls: Literal[0] = 0
