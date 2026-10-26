"""Register a source PDF and persist page text and rendered-page references."""

from __future__ import annotations

from pathlib import Path

from pastport_matched_environment.application.inputs import validate_pdf_file
from pastport_matched_environment.domain.models import ProcessingLimits, ProjectId
from pastport_matched_environment.domain.pdf import PDFPageContent, RegisteredPDF
from pastport_matched_environment.ports.assets import AssetStore
from pastport_matched_environment.ports.pdf import PDFDocumentReader


class PDFIngestionError(ValueError):
    """Raised when PDF registration or extraction cannot produce a complete page set."""


class PDFIngestionService:
    """Coordinate deterministic input preflight, immutable registration and page processing."""

    def __init__(self, asset_store: AssetStore, reader: PDFDocumentReader) -> None:
        self._asset_store = asset_store
        self._reader = reader

    def register_and_extract(
        self,
        project_id: ProjectId,
        pdf_path: Path,
        limits: ProcessingLimits,
    ) -> RegisteredPDF:
        validated_input = validate_pdf_file(pdf_path, limits)
        registered_source = self._asset_store.register_file(
            project_id=project_id,
            source_path=validated_input.path,
            media_type="application/pdf",
            max_bytes=limits.pdf_max_bytes,
        )
        if registered_source.reference.asset.sha256 != validated_input.sha256:
            raise PDFIngestionError("PDF input changed after preflight validation")
        registered_path = self._asset_store.resolve_path(registered_source.reference)
        page_count = self._reader.page_count(registered_path, limits.pdf_max_pages)
        page_contents: list[PDFPageContent] = []
        for draft in self._reader.iter_pages(
            pdf_path=registered_path,
            page_count=page_count,
            max_render_edge=limits.pdf_render_max_edge,
            max_render_bytes=limits.pdf_render_max_bytes,
            render_timeout_seconds=limits.projection_timeout_seconds,
        ):
            if draft.page_index != len(page_contents):
                raise PDFIngestionError("PDF reader returned pages out of sequence")
            rendered_asset = self._asset_store.register_bytes(
                project_id=project_id,
                content=draft.rendered_jpeg,
                media_type="image/jpeg",
                max_bytes=limits.pdf_render_max_bytes,
            )
            page_contents.append(
                PDFPageContent(
                    page_index=draft.page_index,
                    page_width=draft.page_width,
                    page_height=draft.page_height,
                    original_text=draft.original_text,
                    normalized_text=draft.normalized_text,
                    text_lines=draft.text_lines,
                    image_regions=draft.image_regions,
                    extraction_status=draft.extraction_status,
                    rendered_page=rendered_asset.reference,
                )
            )
        return RegisteredPDF(
            source=registered_source.reference,
            page_count=page_count,
            pages=tuple(page_contents),
            extractor_version=self._reader.version,
        )
