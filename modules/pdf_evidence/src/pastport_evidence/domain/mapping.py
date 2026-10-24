"""Internal assigned-object and source-evidence records."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from pastport_evidence.domain.evidence import EvidenceClaim, ExactPassage, HistoricalDescription
from pastport_evidence.domain.models import DomainModel, ProjectAssetRef, ResourceId
from pastport_evidence.domain.photos import PhotoObservation
from pastport_evidence.domain.recognition import SceneEntity


class SourceEvidence(DomainModel):
    """Historical image and independently scoped textual evidence."""

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
    image_association_state: Literal["linked", "candidate"] = "candidate"
    source_image_role: Literal["object_image", "context_image", "text_evidence"] = "object_image"
    source_image: ProjectAssetRef | None = None
    page_image: ProjectAssetRef | None = None
    background: str = ""


class MappedObject(DomainModel):
    entity: SceneEntity
    historical_subject_id: ResourceId | None = None
    draft: HistoricalDescription | None = None
    evidence_refs: tuple[ResourceId, ...] = ()
    source_evidence: SourceEvidence | None = None
    photo_observations: tuple[PhotoObservation, ...] = ()

    @model_validator(mode="after")
    def validate_assignment(self) -> MappedObject:
        if self.draft and self.draft.subject_id != self.historical_subject_id:
            raise ValueError("Description belongs to another historical assignment")
        if (
            self.source_evidence
            and self.source_evidence.historical_subject_id != self.historical_subject_id
        ):
            raise ValueError("Replay evidence belongs to another historical assignment")
        return self
