"""Extract every page as text; render only scans or garbled pages for local OCR."""

from __future__ import annotations

import math
import os
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
from pastport_evidence.ports.ocr import OCRError, PageOCR
from pastport_evidence.adapters.ocr import TesseractPageOCR


class PDFProcessingError(ValueError):
    """Raised when a source PDF cannot be read or a page cannot be rendered."""


class PopplerPDFReader(PDFDocumentReader):
    """Keep source bytes and located lines; page images exist only during OCR."""

    def __init__(self, pdftoppm_path: Path | None = None, *, ocr: PageOCR | None = None) -> None:
        self._pdftoppm_path = pdftoppm_path or Path("pdftoppm")
        self._ocr = ocr if ocr is not None else TesseractPageOCR()

    @property
    def version(self) -> str:
        return (
            f"text-lines-v2;pdfplumber/{pdfplumber.__version__};pypdf/{pypdf_version};"
            f"ocr-languages={os.environ.get('PASTPORT_OCR_LANGUAGES', 'installed-common')}"
        )

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
                    native_text = original_text
                    reason = self.ocr_reason(original_text)
                    # A genuinely blank PDF page is not a scan. Vector-outlined text
                    # and image-backed pages still need OCR when no text is extractable.
                    marked = bool(page.images or page.chars or page.curves or page.rects)
                    result = None
                    if reason is not None and (reason == "garbled" or marked):
                        rendered = self._render_page(
                            pdf_path,
                            page_index,
                            max_render_edge,
                            max_render_bytes,
                            render_timeout_seconds,
                        )
                        try:
                            result = self._ocr.recognize(
                                rendered,
                                float(page.width),
                                float(page.height),
                                render_timeout_seconds,
                            )
                        except OCRError as error:
                            raise PDFProcessingError(
                                f"PDF page {page_index + 1}: {error}"
                            ) from error
                        text_lines = result.lines
                        original_text = "\n".join(line.text for line in text_lines)
                        if self.ocr_reason(original_text) == "garbled":
                            raise PDFProcessingError(
                                f"PDF page {page_index + 1}: OCR text remains garbled"
                            )
                        if not original_text.strip() and reason == "garbled":
                            raise PDFProcessingError(
                                f"PDF page {page_index + 1}: OCR could not recover garbled text"
                            )
                    else:
                        # The persisted line order and canonical text share the same
                        # newline boundaries so line/character citations cannot drift.
                        original_text = (
                            "\n".join(line.text for line in text_lines)
                            if text_lines
                            else original_text
                        )
                    yield PDFPageDraft(
                        page_index=page_index,
                        page_width=float(page.width),
                        page_height=float(page.height),
                        original_text=original_text,
                        normalized_text=_normalize_text(original_text),
                        text_lines=text_lines,
                        image_regions=images,
                        extraction_status=(
                            PDFExtractionStatus.OCR_EXTRACTED
                            if result and original_text.strip()
                            else PDFExtractionStatus.TEXT_EXTRACTED
                            if original_text.strip()
                            else PDFExtractionStatus.EMPTY_PAGE
                        ),
                        native_text=native_text,
                        ocr_engine=result.engine if result else None,
                        ocr_languages=result.languages if result else None,
                        ocr_confidence=result.confidence if result else None,
                        ocr_reason=reason if result else None,
                    )
        except (OSError, PDFSyntaxError, ValueError) as error:
            if isinstance(error, PDFProcessingError):
                raise
            raise PDFProcessingError("PDF page extraction failed") from error

    @staticmethod
    def ocr_reason(text: str) -> str | None:
        visible = [char for char in text if not char.isspace()]
        if not visible:
            return "no_text"
        invalid = sum(
            char == "\ufffd" or unicodedata.category(char) in ("Cc", "Co", "Cn") for char in visible
        )
        mojibake = re.findall(r"Ã[\u0080-\u00bf]|Â[\u0080-\u00bf]|ï»¿|â€™|â€œ|â€", text)
        if (
            invalid / len(visible) >= 0.05
            or re.search(r"\(cid:\d+\)", text)
            or sum(map(len, mojibake)) / len(visible) >= 0.05
        ):
            return "garbled"
        return None

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
