"""Source-native IDML evidence; threaded text is not an inferred printed page."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, model_validator
from pastport_evidence.domain.models import DomainModel, Sha256


class IDMLParagraph(DomainModel):
    index: int
    start: int
    end: int
    text: str
    style: str


class IDMLStory(DomainModel):
    story_id: str
    member: str
    text: str
    paragraphs: tuple[IDMLParagraph, ...]

    @model_validator(mode="after")
    def exact_ranges(self) -> IDMLStory:
        if any(self.text[p.start:p.end] != p.text for p in self.paragraphs):
            raise ValueError("IDML paragraph selectors do not match source text")
        return self


class IDMLPage(DomainModel):
    page_id: str
    label: str
    spread: str
    bounds: tuple[float, float, float, float]


class IDMLFrame(DomainModel):
    frame_id: str
    story_id: str
    previous_frame: str | None
    next_frame: str | None
    spread: str
    group_id: str | None
    bounds: tuple[float, float, float, float] | None
    page_id: str | None
    # IDML threading does not contain composed character offsets per frame.
    text_range_state: Literal["requires_composition"] = "requires_composition"


class IDMLImage(DomainModel):
    image_id: str
    link_id: str
    filename: str
    spread: str
    group_id: str | None
    bounds: tuple[float, float, float, float] | None
    page_id: str | None
    link_state: Literal["available", "missing", "ambiguous", "unsupported"]
    sha256: Sha256 | None


class IDMLAssociationCandidate(DomainModel):
    image_id: str
    frame_ids: tuple[str, ...]
    story_ids: tuple[str, ...]
    basis: Literal["shared_group", "same_page", "same_spread"]
    status: Literal["requires_semantic_review"] = "requires_semantic_review"


class IDMLDocument(DomainModel):
    schema_version: Literal["pastport.idml-source/1"] = "pastport.idml-source/1"
    source_format: Literal["idml"] = "idml"
    source_filename: str
    source_sha256: Sha256
    stories: Annotated[tuple[IDMLStory, ...], Field(max_length=1000)]
    pages: tuple[IDMLPage, ...]
    frames: tuple[IDMLFrame, ...]
    images: tuple[IDMLImage, ...]
    associations: tuple[IDMLAssociationCandidate, ...]
    warnings: tuple[str, ...]
    historical_approval: Literal[False] = False


class IDMLCitationSelection(DomainModel):
    story_id: str
    paragraph_index: int
    quote: Annotated[str, Field(min_length=1, max_length=3000)]


class IDMLHistoricalClaim(DomainModel):
    text: Annotated[str, Field(min_length=1, max_length=350)]
    citations: Annotated[tuple[IDMLCitationSelection, ...], Field(min_length=1, max_length=4)]


class IDMLObjectMatch(DomainModel):
    object_id: str
    status: Literal['matched','unmatched']
    historical_name: str | None
    relationship: Literal['same_kind','functional_analogy','substitution'] | None
    image_id: str | None
    image_role: Literal['object_image','context_image','text_evidence']
    claims: Annotated[tuple[IDMLHistoricalClaim, ...], Field(max_length=4)]
    rationale: Annotated[str, Field(min_length=1,max_length=1000)]
    limitations: tuple[str, ...]

    @model_validator(mode='after')
    def source_required(self) -> IDMLObjectMatch:
        if self.status=='matched' and (not self.historical_name or not self.claims or not self.relationship):
            raise ValueError('A match requires historical identity and cited introduction')
        if self.status=='unmatched' and (self.claims or self.historical_name or self.image_id or self.relationship):
            raise ValueError('Unmatched objects cannot carry accepted historical content')
        return self


class IDMLMatchBatch(DomainModel):
    objects: Annotated[tuple[IDMLObjectMatch, ...], Field(max_length=20)]


class IDMLMatchReview(DomainModel):
    object_id: str
    verdict: Literal['confirmed','rejected','uncertain']
    reason: str


class IDMLMatchReviews(DomainModel):
    objects: Annotated[tuple[IDMLMatchReview, ...], Field(max_length=20)]


class IDMLExactCitation(DomainModel):
    story_id: str
    member: str
    paragraph_index: int
    start: int
    end: int
    quote: str


class IDMLCompiledObject(DomainModel):
    object_id: str
    status: Literal['matched','unmatched','requires_review']
    historical_name: str | None
    relationship: Literal['same_kind','functional_analogy','substitution'] | None
    image_id: str | None
    image_role: Literal['object_image','context_image','text_evidence']
    introduction: str
    citations: tuple[IDMLExactCitation, ...]
    rationale: str
    limitations: tuple[str, ...]
    review_reason: str


class IDMLMatchResult(DomainModel):
    schema_version: Literal['pastport.idml-matches/1'] = 'pastport.idml-matches/1'
    source_sha256: Sha256
    objects: tuple[IDMLCompiledObject, ...]
    receipt_refs: tuple[str, ...]
    historical_approval: Literal[False] = False
