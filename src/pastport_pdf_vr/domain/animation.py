"""Typed image-generation boundary; image edits do not change museum identities."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.models import DomainModel, Sha256


class AnimationImageCommand(DomainModel):
    output_directory: str
    minimum_width: Annotated[int, Field(ge=1, le=8192)] = 1024
    minimum_height: Annotated[int, Field(ge=1, le=8192)] = 1024
    square: bool = True


class AnimationImageResult(DomainModel):
    status: Literal["generated", "rejected"]
    image_path: str | None
    sha256: Sha256 | None
    width: Annotated[int, Field(ge=0)]
    height: Annotated[int, Field(ge=0)]
    reason: str | None = None


class AnimationCapabilities(DomainModel):
    authenticated: bool
    image_generation: bool
    requested_model_available: bool


class ExistingPanorama(DomainModel):
    scene_id: Annotated[str, Field(min_length=1, max_length=200)]
    source_panorama_sha256: Sha256
    image_path: str
    image_sha256: Sha256
    provenance_ref: Annotated[str, Field(min_length=1, max_length=2000)]
