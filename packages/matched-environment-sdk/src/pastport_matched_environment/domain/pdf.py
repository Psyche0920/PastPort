"""Typed records produced while reading and rendering a registered PDF."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from pastport_matched_environment.domain.models import DomainModel, ProjectAssetRef

PageCoordinate = Annotated[float, Field(allow_inf_nan=False)]


class PDFExtractionStatus(StrEnum):
    """Whether native text was found or the page needs a separate OCR stage."""

    TEXT_EXTRACTED = "text_extracted"
    OCR_NEEDED = "ocr_needed"


class PDFRegion(DomainModel):
    """Raw PDF-space bounds; bleed content may extend beyond the visible page."""

    x0: PageCoordinate
    top: PageCoordinate
    x1: PageCoordinate
    bottom: PageCoordinate

    @model_validator(mode="after")
    def validate_bounds(self) -> PDFRegion:
        if self.x1 < self.x0 or self.bottom < self.top:
            raise ValueError("PDF region bounds are inverted")
        return self


class PDFTextLine(DomainModel):
    """One extractable line and its page-space position for exact evidence selectors."""

    line_index: Annotated[int, Field(ge=0)]
    text: Annotated[str, Field(min_length=1)]
    normalized_text: Annotated[str, Field(min_length=1)]
    region: PDFRegion


class PDFImageRegion(DomainModel):
    """Location of an image embedded in the source PDF page."""

    image_index: Annotated[int, Field(ge=0)]
    region: PDFRegion


class PDFPageDraft(DomainModel):
    """Transient page data; rendered bytes are persisted immediately by the application."""

    page_index: Annotated[int, Field(ge=0)]
    page_width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    page_height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    original_text: str
    normalized_text: str
    text_lines: tuple[PDFTextLine, ...]
    image_regions: tuple[PDFImageRegion, ...]
    extraction_status: PDFExtractionStatus
    rendered_jpeg: Annotated[bytes, Field(min_length=1)]


class PDFPageContent(DomainModel):
    """Extracted content and visual evidence from one zero-based PDF page."""

    page_index: Annotated[int, Field(ge=0)]
    page_width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    page_height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    original_text: str
    normalized_text: str
    text_lines: tuple[PDFTextLine, ...]
    image_regions: tuple[PDFImageRegion, ...]
    extraction_status: PDFExtractionStatus
    rendered_page: ProjectAssetRef


class RegisteredPDF(DomainModel):
    """A registered source PDF and its page-indexed extraction/render references."""

    source: ProjectAssetRef
    page_count: Annotated[int, Field(ge=1)]
    pages: tuple[PDFPageContent, ...]
    extractor_version: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_page_sequence(self) -> RegisteredPDF:
        if len(self.pages) != self.page_count:
            raise ValueError("page records must cover the declared PDF page count")
        if any(page.page_index != index for index, page in enumerate(self.pages)):
            raise ValueError("PDF pages must use a complete zero-based page sequence")
        if self.source.project_id != self.pages[0].rendered_page.project_id:
            raise ValueError("rendered pages must belong to the source PDF project")
        if any(page.rendered_page.project_id != self.source.project_id for page in self.pages):
            raise ValueError("rendered pages must belong to the source PDF project")
        return self
