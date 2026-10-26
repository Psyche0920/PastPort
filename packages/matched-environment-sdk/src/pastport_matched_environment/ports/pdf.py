"""PDF processing contract independent of the chosen extraction/render libraries."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from pastport_matched_environment.domain.pdf import PDFPageDraft


class PDFDocumentReader(Protocol):
    """Read and render pages incrementally to keep memory bounded."""

    @property
    def version(self) -> str: ...

    def page_count(self, pdf_path: Path, max_pages: int) -> int: ...

    def iter_pages(
        self,
        pdf_path: Path,
        page_count: int,
        max_render_edge: int,
        max_render_bytes: int,
        render_timeout_seconds: int,
    ) -> Iterator[PDFPageDraft]: ...
