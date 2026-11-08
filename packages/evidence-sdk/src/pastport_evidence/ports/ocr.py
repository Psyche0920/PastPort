"""Local page OCR boundary; no subscription models or source-file mutation."""

from dataclasses import dataclass
from typing import Protocol

from pastport_evidence.domain.pdf import PDFTextLine


class OCRError(ValueError):
    """OCR could not recover trustworthy text within the page limits."""


@dataclass(frozen=True, slots=True)
class OCRResult:
    lines: tuple[PDFTextLine, ...]
    engine: str
    languages: str
    confidence: float | None


class PageOCR(Protocol):
    def recognize(
        self,
        image: bytes,
        page_width: float,
        page_height: float,
        timeout_seconds: int,
    ) -> OCRResult: ...
