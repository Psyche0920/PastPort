"""Automatic PDF/tour build requests and source-bound mapping proposals."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.evidence import ExactPassage, HistoricalSubject
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef, ResourceId
from pastport_pdf_vr.domain.recognition import PixelRegion, SceneEntity


class PDFMatchPage(DomainModel):
    page_index: int
    image: ProjectAssetRef
    width: int
    height: int
    passages: tuple[ExactPassage, ...]


class ObjectReferenceSheet(DomainModel):
    image: ProjectAssetRef
    object_ids: tuple[ResourceId, ...]
    display_numbers: tuple[int, ...]
    columns: int
    rows: int


class PDFMatchRequest(DomainModel):
    mode: Literal["same_site", "demo_substitution"]
    objects: tuple[SceneEntity, ...]
    known_subjects: tuple[HistoricalSubject, ...]
    pages: tuple[PDFMatchPage, ...]
    reference_sheets: Annotated[tuple[ObjectReferenceSheet, ...], Field(max_length=5)] = ()
    grant: SubscriptionGrant
    prompt_version: str = "v1"
    policy_version: str = "pdf-object-mapping-v1"


class PDFObjectMatch(DomainModel):
    object_id: ResourceId
    subject: HistoricalSubject
    page_index: Annotated[int, Field(ge=0)]
    region: PixelRegion | None = None
    passage_ids: tuple[ResourceId, ...]
    relationship: Literal["same_object", "same_kind", "functional_analogy", "substitution"]
    target_scale: Literal["object", "component", "space", "building", "scene"]
    source_scale: Literal["object", "component", "space", "building", "scene"]
    story_support: Literal["documented_activity", "descriptive_only", "unknown"]
    basis: str


class PDFMatchPayload(DomainModel):
    matches: Annotated[tuple[PDFObjectMatch, ...], Field(max_length=200)] = ()
    gaps: Annotated[tuple[str, ...], Field(max_length=200)] = ()


class MappingInventory(DomainModel):
    matches: tuple[PDFObjectMatch, ...]
    pages: tuple[PDFMatchPage, ...]
    receipt_refs: tuple[str, ...]
    gaps: tuple[str, ...]


class BuildSummary(DomainModel):
    project_id: str
    input_binding: str
    mapping_mode: Literal["same_site", "demo_substitution"]
    object_count: int
    anchor_count: int
    gaps: tuple[str, ...]
    status: Literal["completed", "completed_with_gaps"]
