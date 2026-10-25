"""Validated semantic proposals for matched-PDF environment generation."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from pastport_pdf_vr.domain.models import DomainModel, Sha256

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Number = Annotated[int, Field(ge=1)]
Text = Annotated[str, Field(min_length=1, max_length=8000)]
ValidationStage = Literal["matched_pdf", "fresh_localization", "structural_review"]


class PageCrop(DomainModel):
    page: Number
    box: tuple[Unit, Unit, Unit, Unit]
    basis: Text

    @model_validator(mode="after")
    def ordered(self) -> "PageCrop":
        if self.box[0] >= self.box[2] or self.box[1] >= self.box[3]:
            raise ValueError("Evidence crop must have positive area")
        return self


class PDFEntryLabel(DomainModel):
    number: Number
    history_key: Text
    detail_page: Number


class PDFIndexEntry(PDFEntryLabel):
    modern_images: Annotated[tuple[PageCrop, ...], Field(max_length=100)]


class MatchedPDFIndex(DomainModel):
    entries: Annotated[tuple[PDFIndexEntry, ...], Field(max_length=200)]
    basis: Text


class MatchedObject(DomainModel):
    number: Number
    name: Annotated[str, Field(min_length=1, max_length=100)]
    boundary: Text
    history_key: Text
    history: Annotated[str, Field(min_length=1, max_length=200)]
    parent: Text
    page: Number
    quote: str
    historical_image: PageCrop | None
    modern_images: Annotated[tuple[PageCrop, ...], Field(min_length=1, max_length=100)]
    explanation: Annotated[str, Field(min_length=1, max_length=300)]
    proxy: Annotated[str, Field(min_length=1, max_length=300)]
    limitation: Annotated[str, Field(min_length=1, max_length=300)]
    whole_number: Number | None
    historical_relation: Literal["fixed_part_of", "contained_in"] | None

    @model_validator(mode="after")
    def relation(self) -> "MatchedObject":
        if self.whole_number is not None and self.historical_relation is None:
            raise ValueError("A mapped whole identity requires its historical relationship")
        if self.whole_number == self.number:
            raise ValueError("An entity cannot be its own whole")
        if not self.quote.strip() and self.historical_image is None:
            raise ValueError("Historical evidence is required")
        return self


class MatchedBatch(DomainModel):
    objects: Annotated[tuple[MatchedObject, ...], Field(max_length=200)]
    gaps: Annotated[tuple[str, ...], Field(max_length=200)]


class VisualIdentity(DomainModel):
    number: Number
    name: str
    boundary: str


class RelationalIdentity(DomainModel):
    number: Number
    name: str
    boundary: str
    history: str
    parent: str
    quote: str
    limitation: str
    whole_number: Number | None
    historical_relation: Literal["fixed_part_of", "contained_in"] | None
    modern_images: tuple[PageCrop, ...] = ()


class ProposedLocation(DomainModel):
    number: Number
    status: Literal["visible", "not_visible", "uncertain"]
    projection_index: Annotated[int, Field(ge=0, le=6)] | None
    center: tuple[Unit, Unit] | None
    basis: Text

    @model_validator(mode="after")
    def measured(self) -> "ProposedLocation":
        if self.status == "visible" and (self.center is None or self.projection_index is None):
            raise ValueError("Visible objects need a measured point and projection")
        if self.status != "visible" and (
            self.center is not None or self.projection_index is not None
        ):
            raise ValueError("Unconfirmed objects cannot have coordinates")
        return self


class LocationBatch(DomainModel):
    objects: Annotated[tuple[ProposedLocation, ...], Field(max_length=16)]


class LocationReview(DomainModel):
    number: Number
    verdict: Literal["confirmed", "rejected", "uncertain"]
    reason: Text


class LocationReviews(DomainModel):
    objects: Annotated[tuple[LocationReview, ...], Field(max_length=16)]


class HistoricalRelation(DomainModel):
    whole_object_number: Number
    part_object_number: Number
    historical_relation: Literal["fixed_part_of", "contained_in"]
    reason: Text


class RelationInventory(DomainModel):
    relations: Annotated[tuple[HistoricalRelation, ...], Field(max_length=200)]
    review_basis: Text


class StructuralVerdict(DomainModel):
    modern_relation: Literal["within_whole", "attached_to_whole", "unrelated", "not_confirmed"]
    verdict: Literal["verified", "rejected", "pending"]
    reason: Text


class RunResultPointer(DomainModel):
    project_id: str
    source_binding: Sha256
    grant_binding: Sha256
    result_run_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")]
