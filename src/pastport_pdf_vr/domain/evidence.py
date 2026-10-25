"""Exact quotations, independently scoped claims and editable display copy."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef, ResourceId
from pastport_pdf_vr.domain.pdf import PDFRegion

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class EvidenceScope(StrEnum):
    DIRECT = "direct"
    PARENT_BACKGROUND = "parent_background"
    GENERAL_CONTEXT = "general_context"


class ExactPassage(DomainModel):
    passage_id: ResourceId
    source: ProjectAssetRef
    page_index: Annotated[int, Field(ge=0)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    quote: Annotated[str, Field(min_length=1, max_length=8000)]

    @model_validator(mode="after")
    def validate_selector(self) -> ExactPassage:
        if self.end - self.start != len(self.quote):
            raise ValueError("Exact quote and character selector disagree")
        return self


class HistoricalSubject(DomainModel):
    subject_id: ResourceId
    label: Text
    parent_subject_id: ResourceId | None = None
    retrieval_terms: tuple[Text, ...] = ()


class SourceImageObservation(DomainModel):
    image_id: ResourceId
    source: ProjectAssetRef
    page_index: Annotated[int, Field(ge=0)]
    region: PDFRegion
    description: Text
    depiction: Literal["component", "whole_structure", "scene", "page_context", "unclassified"] = (
        "unclassified"
    )
    depicted_subject_id: ResourceId | None = None


class EvidenceClaim(DomainModel):
    claim_id: ResourceId
    subject_id: ResourceId
    scope: EvidenceScope
    statement: Text
    passage_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1)]


class ImageAssociation(DomainModel):
    image_id: ResourceId
    subject_id: ResourceId
    passage_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1)]
    basis: Text
    scope: EvidenceScope = EvidenceScope.DIRECT


class EvidencePayload(DomainModel):
    associations: Annotated[tuple[ImageAssociation, ...], Field(max_length=40)]
    claims: Annotated[tuple[EvidenceClaim, ...], Field(max_length=200)]
    retrieval_queries: Annotated[tuple[Text, ...], Field(max_length=4)] = ()


class EvidenceProposal(EvidencePayload):
    """Validated model payload plus a receipt supplied by the execution adapter."""

    receipt_ref: ResourceId


class EvidenceAssessment(DomainModel):
    """Accepted proposal and explicit rejected-item diagnostics; raw receipts stay immutable."""

    proposal: EvidenceProposal
    validation_gaps: tuple[str, ...] = ()


class DisplaySentence(DomainModel):
    text: Text
    claim_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1)]


class PopupPayload(DomainModel):
    subject_id: ResourceId
    introduction: Annotated[tuple[DisplaySentence, ...], Field(max_length=4)] = ()
    background: Annotated[tuple[DisplaySentence, ...], Field(max_length=8)] = ()


class PopupProposal(PopupPayload):
    receipt_ref: ResourceId


class EvidenceSelection(DomainModel):
    subject: HistoricalSubject
    passages: Annotated[tuple[ExactPassage, ...], Field(max_length=40)]
    image: SourceImageObservation | None = None
    policy_version: Text
    prompt_version: Text
    grant_ref: ResourceId
    model_id: Text


class DraftRequest(DomainModel):
    selection: EvidenceSelection
    claims: tuple[EvidenceClaim, ...]


class AssociatedEvidence(DomainModel):
    selection: EvidenceSelection
    evidence: EvidenceProposal
    retrieval_rounds: Literal[1, 2]
    retrieval_gap: bool
    receipt_refs: tuple[ResourceId, ...]
    validation_gaps: tuple[str, ...] = ()


class DisplayCopy(DomainModel):
    subject_id: ResourceId
    version: Annotated[int, Field(ge=1)]
    introduction: str
    background: str = ""


class EffectiveCopy(DomainModel):
    content: DisplayCopy | None
    origin: Literal["human", "ai", "unbound"]
    assignment_mismatch: bool = False
