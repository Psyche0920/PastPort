"""Scene identities, image-bound proposals and complete per-view dispositions."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from pastport_evidence.domain.evidence import Text
from pastport_evidence.domain.geometry import PixelPoint
from pastport_evidence.domain.models import DomainModel, ResourceId


class SceneEntity(DomainModel):
    object_id: ResourceId
    display_number: Annotated[int, Field(ge=1)]
    label: Text
    category: Text
    distinguishing_features: Annotated[tuple[Text, ...], Field(min_length=1)]
    parent_object_id: ResourceId | None = None


class EntityProposal(DomainModel):
    proposal_id: ResourceId
    label: Text
    category: Text
    distinguishing_features: Annotated[tuple[Text, ...], Field(min_length=1)]
    existing_object_id: ResourceId | None = None
    same_identity_evidence: tuple[Text, ...] = ()
    parent_ref: ResourceId | None = None

    @model_validator(mode="after")
    def validate_identity_link(self) -> EntityProposal:
        if self.existing_object_id and (not self.same_identity_evidence):
            raise ValueError("Cross-view identity reuse requires distinguishing evidence")
        return self


class PixelRegion(DomainModel):
    top_left: PixelPoint
    bottom_right: PixelPoint

    @model_validator(mode="after")
    def validate_area(self) -> PixelRegion:
        if self.top_left.x >= self.bottom_right.x or self.top_left.y >= self.bottom_right.y:
            raise ValueError("Selected image region must have positive area")
        return self


class RecognitionResult(DomainModel):
    entities: tuple[SceneEntity, ...]
    calls_used: int
    gaps: tuple[str, ...]
