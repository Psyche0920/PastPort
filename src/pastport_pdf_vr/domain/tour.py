"""Imported tours preserve navigation and decoded panorama identity."""

from typing import Annotated

from pydantic import Field, model_validator

from pastport_pdf_vr.domain.geometry import SphericalPoint
from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef, ResourceId


class TourLink(DomainModel):
    target_view_id: ResourceId
    position: SphericalPoint
    label: str


class TourView(DomainModel):
    view_id: ResourceId
    label: str
    panorama: ProjectAssetRef
    revision: Annotated[int, Field(ge=1)]
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    initial_position: SphericalPoint
    links: tuple[TourLink, ...]


class ImportedTour(DomainModel):
    tour_id: ResourceId
    source: ProjectAssetRef
    schema_version: int
    first_view_id: ResourceId
    views: Annotated[tuple[TourView, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def validate_closure(self) -> "ImportedTour":
        ids = {view.view_id for view in self.views}
        if len(ids) != len(self.views) or self.first_view_id not in ids:
            raise ValueError("Tour view identities or first view are invalid")
        if self.schema_version not in (3, 4):
            raise ValueError("Only declared tour schema versions 3 and 4 are supported")
        if any(view.panorama.project_id != self.source.project_id for view in self.views):
            raise ValueError("Tour media belongs to another project")
        if any(link.target_view_id not in ids for view in self.views for link in view.links):
            raise ValueError("Tour navigation points to an unknown view")
        return self
