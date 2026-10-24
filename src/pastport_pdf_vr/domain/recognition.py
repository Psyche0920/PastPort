"""Scene identities, image-bound proposals and complete per-view dispositions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from pastport_pdf_vr.domain.evidence import Text
from pastport_pdf_vr.domain.geometry import AnchorPosition, ImageTransform, PixelPoint
from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef, ProjectId, ResourceId


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
        if self.existing_object_id and not self.same_identity_evidence:
            raise ValueError("Cross-view identity reuse requires distinguishing evidence")
        return self


class MatchingImage(DomainModel):
    image_id: ResourceId
    view_id: ResourceId
    image: ProjectAssetRef
    panorama: ProjectAssetRef
    panorama_revision: Annotated[int, Field(ge=1)]
    transform: ImageTransform
    inspection_level: Literal["overview", "detail"]

    @model_validator(mode="after")
    def validate_project(self) -> MatchingImage:
        if self.image.project_id != self.panorama.project_id:
            raise ValueError("Matching image and panorama project differ")
        return self


class PanoramaView(DomainModel):
    view_id: ResourceId
    panorama: ProjectAssetRef
    panorama_revision: Annotated[int, Field(ge=1)]
    images: Annotated[tuple[MatchingImage, ...], Field(min_length=1, max_length=24)]

    @model_validator(mode="after")
    def validate_images(self) -> PanoramaView:
        if len({image.image_id for image in self.images}) != len(self.images):
            raise ValueError("Matching image IDs must be unique")
        if any(
            image.view_id != self.view_id
            or image.panorama != self.panorama
            or image.panorama_revision != self.panorama_revision
            for image in self.images
        ):
            raise ValueError("Matching image is bound to another view/panorama revision")
        return self


class PixelRegion(DomainModel):
    top_left: PixelPoint
    bottom_right: PixelPoint

    @model_validator(mode="after")
    def validate_area(self) -> PixelRegion:
        if self.top_left.x >= self.bottom_right.x or self.top_left.y >= self.bottom_right.y:
            raise ValueError("Selected image region must have positive area")
        return self


class SightingProposal(DomainModel):
    target_ref: ResourceId
    image_id: ResourceId
    disposition: Literal[
        "located", "ambiguous_identity", "insufficient_resolution", "occluded", "not_seen"
    ]
    role: Literal["environment", "screen_content"] = "environment"
    point: PixelPoint | None = None
    region: PixelRegion | None = None
    basis: Annotated[tuple[Text, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_location(self) -> SightingProposal:
        if self.disposition == "located":
            if self.point is None or self.region is None:
                raise ValueError("Located sighting requires a region and selected anchor point")
            if not (
                self.region.top_left.x <= self.point.x <= self.region.bottom_right.x
                and self.region.top_left.y <= self.point.y <= self.region.bottom_right.y
            ):
                raise ValueError("Selected anchor point lies outside its subject region")
        elif self.point is not None or self.region is not None:
            raise ValueError("Unresolved sightings cannot carry guessed geometry")
        return self


class SceneInspectionPayload(DomainModel):
    entities: Annotated[tuple[EntityProposal, ...], Field(max_length=200)] = ()
    sightings: Annotated[tuple[SightingProposal, ...], Field(max_length=1600)] = ()


class SceneInspection(SceneInspectionPayload):
    """Model payload with a trusted gateway receipt attached outside model generation."""

    receipt_ref: ResourceId


class SceneInspectionRequest(DomainModel):
    project_id: ProjectId
    view_id: ResourceId
    phase: Literal["initial", "recheck"]
    images: Annotated[tuple[MatchingImage, ...], Field(min_length=1, max_length=8)]
    catalog: Annotated[tuple[SceneEntity, ...], Field(max_length=1000)]
    target_ids: Annotated[tuple[ResourceId, ...], Field(max_length=100)] = ()
    grant_ref: ResourceId
    model_id: Text
    prompt_version: Text
    policy_version: Text


class ViewDisposition(DomainModel):
    object_id: ResourceId
    view_id: ResourceId
    panorama: ProjectAssetRef
    panorama_revision: Annotated[int, Field(ge=1)]
    state: Literal[
        "located",
        "ambiguous_identity",
        "ambiguous_position",
        "insufficient_resolution",
        "occluded",
        "not_seen_after_review",
        "not_inspected",
        "confirmed_absent",
        "screen_content",
        "outside_anchor_range",
    ]
    position: AnchorPosition | None = None
    image_ids: tuple[ResourceId, ...] = ()
    basis: tuple[Text, ...] = ()
    rechecked: bool = False

    @model_validator(mode="after")
    def validate_anchor(self) -> ViewDisposition:
        if (self.state == "located") != (self.position is not None):
            raise ValueError("Only located environmental sightings can carry an anchor")
        return self


class RecognitionResult(DomainModel):
    entities: tuple[SceneEntity, ...]
    dispositions: tuple[ViewDisposition, ...]
    calls_used: Annotated[int, Field(ge=0)]
    gaps: tuple[str, ...]
