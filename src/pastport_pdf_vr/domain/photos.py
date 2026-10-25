"""Ordinary photographs and pixel observations, independent of panorama geometry."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef
from pastport_pdf_vr.domain.recognition import EntityProposal, PixelRegion, SceneEntity


class ScenePhoto(DomainModel):
    photo_id: str
    name: str
    original: ProjectAssetRef
    image: ProjectAssetRef
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class PhotoSighting(DomainModel):
    target_ref: str
    photo_id: str
    region: PixelRegion
    identity_state: Literal["confirmed", "uncertain"] = "confirmed"
    basis: str


class PhotoObservation(DomainModel):
    object_id: str
    photo: ScenePhoto
    region: PixelRegion
    crop: ProjectAssetRef
    identity_state: Literal["confirmed", "uncertain"]
    basis: str


class PhotoReference(DomainModel):
    object_id: str
    image: ProjectAssetRef
    basis: str


class PhotoInspectionRequest(DomainModel):
    photos: Annotated[tuple[ScenePhoto, ...], Field(min_length=1, max_length=4)]
    references: Annotated[tuple[PhotoReference, ...], Field(max_length=4)] = ()
    catalog: tuple[SceneEntity, ...] = ()
    phase: Literal["inventory", "recheck"] = "inventory"
    grant_ref: str
    model_id: str


class PhotoInspectionPayload(DomainModel):
    entities: Annotated[tuple[EntityProposal, ...], Field(max_length=100)] = ()
    sightings: Annotated[tuple[PhotoSighting, ...], Field(max_length=200)] = ()
    gaps: tuple[str, ...] = ()


class PhotoInspection(PhotoInspectionPayload):
    receipt_ref: str


class PhotoInventory(DomainModel):
    photos: tuple[ScenePhoto, ...]
    entities: tuple[SceneEntity, ...] = ()
    observations: tuple[PhotoObservation, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
