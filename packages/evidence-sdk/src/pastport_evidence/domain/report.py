"""Internal layout shared by the two document renderers, not a downstream API."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TextFrame:
    text: str
    x: float
    y: float
    width: float
    height: float
    font_size: float = 10.0
    link: str | None = None


@dataclass(frozen=True, slots=True)
class ImageFrame:
    path: Path
    x: float
    y: float
    width: float
    height: float
    caption: str


@dataclass(frozen=True, slots=True)
class ReportPage:
    texts: tuple[TextFrame, ...]
    images: tuple[ImageFrame, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportDocument:
    pages: tuple[ReportPage, ...]
    width: float = 842.0
    height: float = 595.0
