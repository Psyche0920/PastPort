"""Live preview records and independent versioned human text/geometry overrides."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from pastport_pdf_vr.domain.evidence import DisplayCopy, EvidenceClaim, ExactPassage
from pastport_pdf_vr.domain.geometry import AnchorPosition
from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef, ProjectId, ResourceId
from pastport_pdf_vr.domain.photos import PhotoObservation
from pastport_pdf_vr.domain.recognition import SceneEntity


class ReplayEvidence(DomainModel):
    """Source evidence; the legacy class/field name is retained for preview compatibility."""

    historical_subject_id: ResourceId
    title: str
    pdf_page_number: Annotated[int, Field(ge=1)]
    printed_page: int | None
    original_quote: str
    translation: str
    scope: str
    limitation: str
    source_page_sha256: str
    quote_representation: Literal["legacy_normalized_page", "raw_page"] = "legacy_normalized_page"
    source_ref: ProjectAssetRef | None = None
    passages: tuple[ExactPassage, ...] = ()
    claims: tuple[EvidenceClaim, ...] = ()
    source_image: ProjectAssetRef | None = None
    page_image: ProjectAssetRef | None = None
    background: str = ""


class PreviewObject(DomainModel):
    entity: SceneEntity
    historical_subject_id: ResourceId | None = None
    draft: DisplayCopy | None = None
    evidence_refs: tuple[ResourceId, ...] = ()
    replay_evidence: ReplayEvidence | None = None
    photo_observations: tuple[PhotoObservation, ...] = ()

    @model_validator(mode="after")
    def validate_assignment(self) -> PreviewObject:
        if self.draft and self.draft.subject_id != self.historical_subject_id:
            raise ValueError("Popup draft belongs to another historical assignment")
        if (
            self.replay_evidence
            and self.replay_evidence.historical_subject_id != self.historical_subject_id
        ):
            raise ValueError("Replay evidence belongs to another historical assignment")
        return self


class PreviewAnchor(DomainModel):
    object_id: ResourceId
    view_id: ResourceId
    panorama: ProjectAssetRef
    panorama_revision: Annotated[int, Field(ge=1)]
    position: AnchorPosition


class TextEdit(DomainModel):
    operation_id: ResourceId
    object_id: ResourceId
    historical_subject_id: ResourceId
    expected_version: Annotated[int, Field(ge=0)]
    introduction: Annotated[str, Field(max_length=1200)]
    background: Annotated[str, Field(max_length=6000)] = ""


class PositionEdit(DomainModel):
    operation_id: ResourceId
    object_id: ResourceId
    view_id: ResourceId
    panorama: ProjectAssetRef
    panorama_revision: Annotated[int, Field(ge=1)]
    expected_version: Annotated[int, Field(ge=0)]
    position: AnchorPosition


class EditResult(DomainModel):
    operation_id: ResourceId
    version: Annotated[int, Field(ge=1)]
    project_revision: Annotated[int, Field(ge=1)]


class EffectiveObject(DomainModel):
    object: PreviewObject
    introduction: str
    background: str
    origin: Literal["human", "ai", "unbound"]
    version: Annotated[int, Field(ge=0)]
    assignment_mismatch: bool = False


class EffectiveAnchor(DomainModel):
    anchor: PreviewAnchor
    position: AnchorPosition
    origin: Literal["human", "model"]
    version: Annotated[int, Field(ge=0)]


class PreviewSnapshot(DomainModel):
    project_id: ProjectId
    revision: Annotated[int, Field(ge=1)]
    input_binding: ResourceId
    mode: Literal["synthetic_replay", "model_generated"]
    objects: tuple[EffectiveObject, ...]
    anchors: tuple[EffectiveAnchor, ...]
