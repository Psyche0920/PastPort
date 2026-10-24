"""Immutable domain records shared by input, workflow and export boundaries."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ProjectId = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=100, pattern="^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
]
RunId = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=100, pattern="^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
]
ResourceId = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=200, pattern="^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    ),
]
Sha256 = Annotated[str, StringConstraints(strict=True, pattern="^[a-f0-9]{64}$")]


class DomainModel(BaseModel):
    """Base for immutable, strict records that cross internal boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class AssetRef(DomainModel):
    """Immutable reference to registered bytes; never a workstation path."""

    resource_id: ResourceId
    version: Annotated[int, Field(ge=1)]
    sha256: Sha256


class ProjectAssetRef(DomainModel):
    """Asset reference bound to the project that registered it."""

    project_id: ProjectId
    asset: AssetRef


class RegisteredAsset(DomainModel):
    """Project-bound reference plus storage metadata for immutable registered bytes."""

    reference: ProjectAssetRef
    media_type: Annotated[str, StringConstraints(strict=True, min_length=3, max_length=100)]
    byte_length: Annotated[int, Field(ge=1)]


class ProcessingLimits(DomainModel):
    """Explicit operational ceilings; provider limits may require lower values."""

    pdf_max_bytes: Annotated[int, Field(ge=1, le=512 * 1024 * 1024)] = 64 * 1024 * 1024
    pdf_max_pages: Annotated[int, Field(ge=1, le=500)] = 500
    pdf_render_max_edge: Annotated[int, Field(ge=256, le=2048)] = 2048
    pdf_render_max_bytes: Annotated[int, Field(ge=1, le=16 * 1024 * 1024)] = 16 * 1024 * 1024
    render_timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 120
