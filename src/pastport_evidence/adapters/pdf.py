"""Native PDF text, positioned line and embedded image extraction plus Poppler rendering."""

from __future__ import annotations

import math
import re
import subprocess
import unicodedata
from collections.abc import Iterator, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pypdf import PdfReader
from pypdf import __version__ as pypdf_version
from pypdf.errors import PdfReadError

from pastport_evidence.domain.pdf import (
    PDFExtractionStatus,
    PDFImageRegion,
    PDFPageDraft,
    PDFRegion,
    PDFTextLine,
)
from pastport_evidence.ports.pdf import PDFDocumentReader


class PDFProcessingError(ValueError):
    """Raised when a source PDF cannot be read or a page cannot be rendered."""


class PopplerPDFReader(PDFDocumentReader):
    """Extract text with pdfplumber and render page images with an injected Poppler binary."""

    def __init__(self, pdftoppm_path: Path) -> None:
        self._pdftoppm_path = pdftoppm_path

    @property
    def version(self) -> str:
        return f"pdfplumber/{pdfplumber.__version__};pypdf/{pypdf_version}"

    def page_count(self, pdf_path: Path, max_pages: int) -> int:
        try:
            with pdf_path.open("rb") as pdf_stream:
                reader = PdfReader(pdf_stream, strict=True)
                if reader.is_encrypted:
                    raise PDFProcessingError("Encrypted PDF documents are not supported")
                count = len(reader.pages)
        except (OSError, PdfReadError, PDFSyntaxError) as error:
            raise PDFProcessingError("PDF page count could not be read") from error
        if count < 1:
            raise PDFProcessingError("PDF contains no pages")
        if count > max_pages:
            raise PDFProcessingError("PDF page count exceeds the configured limit")
        return count

    def iter_pages(
        self,
        pdf_path: Path,
        page_count: int,
        max_render_edge: int,
        max_render_bytes: int,
        render_timeout_seconds: int,
    ) -> Iterator[PDFPageDraft]:
        try:
            with pdfplumber.open(pdf_path) as document:
                if len(document.pages) != page_count:
                    raise PDFProcessingError(
                        "PDF page count changed between validation and extraction"
                    )
                for page_index, page in enumerate(document.pages):
                    original_text = page.extract_text(layout=False) or ""
                    line_records = _library_records(
                        page.extract_text_lines(return_chars=False) or []
                    )
                    text_lines = tuple(
                        self._text_line(record, index) for index, record in enumerate(line_records)
                    )
                    images = tuple(
                        self._image_region(record, index)
                        for index, record in enumerate(_library_records(page.images))
                    )
                    normalized_text = _normalize_text(original_text)
                    rendered_jpeg = self._render_page(
                        pdf_path,
                        page_index,
                        max_render_edge,
                        max_render_bytes,
                        render_timeout_seconds,
                    )
                    yield PDFPageDraft(
                        page_index=page_index,
                        page_width=float(page.width),
                        page_height=float(page.height),
                        original_text=original_text,
                        normalized_text=normalized_text,
                        text_lines=text_lines,
                        image_regions=images,
                        extraction_status=(
                            PDFExtractionStatus.TEXT_EXTRACTED
                            if normalized_text
                            else PDFExtractionStatus.OCR_NEEDED
                        ),
                        rendered_jpeg=rendered_jpeg,
                    )
        except (OSError, PDFSyntaxError, ValueError) as error:
            if isinstance(error, PDFProcessingError):
                raise
            raise PDFProcessingError("PDF page extraction failed") from error

    def _render_page(
        self,
        pdf_path: Path,
        page_index: int,
        max_render_edge: int,
        max_render_bytes: int,
        timeout_seconds: int,
    ) -> bytes:
        with TemporaryDirectory(prefix="pastport-pdf-render-") as temporary_directory:
            output_prefix = Path(temporary_directory) / "page"
            command = [
                str(self._pdftoppm_path),
                "-f",
                str(page_index + 1),
                "-l",
                str(page_index + 1),
                "-scale-to",
                str(max_render_edge),
                "-singlefile",
                "-jpeg",
                "-jpegopt",
                "quality=88",
                str(pdf_path),
                str(output_prefix),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_seconds,
                )
            except FileNotFoundError as error:
                raise PDFProcessingError("Poppler pdftoppm executable is unavailable") from error
            except subprocess.TimeoutExpired as error:
                raise PDFProcessingError("PDF page rendering exceeded its time limit") from error
            if completed.returncode != 0:
                raise PDFProcessingError("Poppler could not render the requested PDF page")
            rendered_path = output_prefix.with_suffix(".jpg")
            try:
                rendered_bytes = rendered_path.read_bytes()
            except OSError as error:
                raise PDFProcessingError("Rendered PDF page image is missing") from error
            if not rendered_bytes or len(rendered_bytes) > max_render_bytes:
                raise PDFProcessingError("Rendered PDF page is empty or exceeds its byte limit")
            return rendered_bytes

    @staticmethod
    def _text_line(record: Mapping[str, object], line_index: int) -> PDFTextLine:
        text = _required_text(record, "text")
        return PDFTextLine(
            line_index=line_index,
            text=text,
            normalized_text=_normalize_text(text),
            region=PDFRegion(
                x0=_required_number(record, "x0"),
                top=_required_number(record, "top"),
                x1=_required_number(record, "x1"),
                bottom=_required_number(record, "bottom"),
            ),
        )

    @staticmethod
    def _image_region(record: Mapping[str, object], image_index: int) -> PDFImageRegion:
        return PDFImageRegion(
            image_index=image_index,
            region=PDFRegion(
                x0=_required_number(record, "x0"),
                top=_required_number(record, "top"),
                x1=_required_number(record, "x1"),
                bottom=_required_number(record, "bottom"),
            ),
        )


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    return "\n".join(
        re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()
    ).strip()


def _required_text(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise PDFProcessingError(f"PDF extraction library returned an invalid {field_name} value")
    return value


def _required_number(record: Mapping[str, object], field_name: str) -> float:
    value = record.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PDFProcessingError(f"PDF extraction library returned an invalid {field_name} value")
    return float(value)


def _library_records(values: object) -> tuple[Mapping[str, object], ...]:
    """Convert loosely typed third-party extraction values at the adapter boundary."""
    if not isinstance(values, list):
        raise PDFProcessingError("PDF extraction library returned an invalid record list")
    records: list[Mapping[str, object]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise PDFProcessingError("PDF extraction library returned a malformed record")
        records.append(cast(Mapping[str, object], value))
    return tuple(records)
