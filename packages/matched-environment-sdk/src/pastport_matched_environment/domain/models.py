"""Immutable domain records shared by input, workflow and export boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

ProjectId = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
]
RunId = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
]
ResourceId = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    ),
]
Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]


class DomainModel(BaseModel):
    """Base for immutable, strict records that cross internal boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class InputRepresentation(StrEnum):
    """Declares whether a run matches real-site material or a synthetic replay."""

    REAL_SITE = "real_site"
    SYNTHETIC_REPLAY = "synthetic_replay"


class RunStatus(StrEnum):
    """Lifecycle of a complete pipeline run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_GAPS = "completed_with_gaps"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_REQUIRED = "recovery_required"


class StageStatus(StrEnum):
    """Durable lifecycle of one pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISPATCH_UNKNOWN = "dispatch_unknown"


class AssociationState(StrEnum):
    """Public SDK-compatible association states for a source record."""

    LINKED = "linked"
    CANDIDATE = "candidate"
    TEXT_ONLY = "text_only"
    IMAGE_ONLY = "image_only"


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


class SourceLocator(DomainModel):
    """Exact source position for evidence in an immutable document version."""

    source_ref: AssetRef
    page_index: Annotated[int, Field(ge=0)]
    printed_page: Annotated[str, StringConstraints(strict=True, max_length=80)] | None = None
    paragraph_id: Annotated[str, StringConstraints(strict=True, max_length=100)] | None = None
    region_id: Annotated[str, StringConstraints(strict=True, max_length=100)] | None = None


class SourceRecord(DomainModel):
    """One image/text evidence record, separate from the historical subject identity."""

    record_id: ResourceId
    project_id: ProjectId
    image: AssetRef | None = None
    text: Annotated[str, StringConstraints(strict=True, min_length=1)] | None = None
    language: Annotated[str, StringConstraints(strict=True, min_length=2, max_length=35)]
    locator: SourceLocator
    association_state: AssociationState
    association_basis: Annotated[str, StringConstraints(strict=True, min_length=1)] | None = None

    @field_validator("text")
    @classmethod
    def text_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("text cannot contain only whitespace")
        return value

    @model_validator(mode="after")
    def validate_association_payload(self) -> SourceRecord:
        has_image = self.image is not None
        has_text = self.text is not None
        consistent = {
            AssociationState.LINKED: has_image and has_text,
            AssociationState.CANDIDATE: has_image or has_text,
            AssociationState.TEXT_ONLY: has_text and not has_image,
            AssociationState.IMAGE_ONLY: has_image and not has_text,
        }[self.association_state]
        if not consistent:
            raise ValueError("image/text fields do not agree with association_state")
        if self.association_state is AssociationState.CANDIDATE and self.association_basis is None:
            raise ValueError("candidate association requires an explicit association_basis")
        return self


class ProcessingLimits(DomainModel):
    """Explicit operational ceilings; provider limits may require lower values."""

    pdf_max_bytes: Annotated[int, Field(ge=1, le=512 * 1024 * 1024)] = 64 * 1024 * 1024
    pdf_max_pages: Annotated[int, Field(ge=1, le=500)] = 500
    pdf_render_max_edge: Annotated[int, Field(ge=256, le=2048)] = 2048
    pdf_render_max_bytes: Annotated[int, Field(ge=1, le=16 * 1024 * 1024)] = 16 * 1024 * 1024
    tour_max_compressed_bytes: Annotated[int, Field(ge=1, le=150 * 1024 * 1024)] = 150 * 1024 * 1024
    tour_max_expanded_bytes: Annotated[int, Field(ge=1, le=200 * 1024 * 1024)] = 200 * 1024 * 1024
    tour_max_members: Annotated[int, Field(ge=1, le=100)] = 100
    panorama_max_bytes: Annotated[int, Field(ge=1, le=16 * 1024 * 1024)] = 16 * 1024 * 1024
    panorama_max_pixels: Annotated[int, Field(ge=1, le=64_000_000)] = 64_000_000
    derived_views_per_view: Annotated[int, Field(ge=0, le=24)] = 24
    derived_view_longest_edge: Annotated[int, Field(ge=256, le=2048)] = 2048
    model_images_per_request: Annotated[int, Field(ge=1, le=8)] = 8
    model_image_max_bytes: Annotated[int, Field(ge=1, le=4 * 1024 * 1024)] = 4 * 1024 * 1024
    localization_rounds_per_record: Annotated[int, Field(ge=1, le=2)] = 2
    network_timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 60
    projection_timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 120
    stage_timeout_seconds: Annotated[int, Field(ge=1, le=1800)] = 1800
    max_model_calls: Annotated[int, Field(ge=1, le=10_000)]
    budget_usd: Annotated[Decimal, Field(gt=Decimal("0"), max_digits=10, decimal_places=4)]

    @field_validator("budget_usd")
    @classmethod
    def budget_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("budget_usd must be finite")
        return value


class ProjectConfig(DomainModel):
    """Non-secret, project-scoped runtime configuration."""

    project_id: ProjectId
    input_representation: InputRepresentation
    provider: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]
    model_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=160)]
    prompt_version: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]
    policy_version: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]
    limits: ProcessingLimits


class RunRequest(DomainModel):
    """Idempotent command binding one run to registered project inputs."""

    request_id: RunId
    project_id: ProjectId
    pdf_ref: ProjectAssetRef
    tour_ref: ProjectAssetRef
    config_version: Annotated[int, Field(ge=1)]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at")
    @classmethod
    def datetime_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @field_validator("pdf_ref", "tour_ref")
    @classmethod
    def assets_must_belong_to_run_project(
        cls, value: ProjectAssetRef, info: ValidationInfo
    ) -> ProjectAssetRef:
        run_project_id = info.data.get("project_id")
        if run_project_id is not None and value.project_id != run_project_id:
            raise ValueError("input asset belongs to a different project")
        return value
