"""Export reviewed publication photographs for the local game scenes."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import io
import fitz  # type: ignore[import-untyped]  # PyMuPDF has no bundled typing metadata.
from PIL import Image

class PhotoExportError(RuntimeError):
    """Raised when publication images cannot be exported safely."""


@dataclass(frozen=True)
class Photograph:
    filename: str
    pdf_page: int
    image_index: int

class PhotoExporter:
    """Retain the full photograph framing while limiting web download size."""
    def export(self, source: Path, destination: Path, photos: tuple[Photograph, ...]) -> None:
        try:
            destination.mkdir(parents=True, exist_ok=True)
            with fitz.open(source) as document:
                for photo in photos:
                    image_records = document[photo.pdf_page - 1].get_images(full=True)
                    original = document.extract_image(image_records[photo.image_index][0])
                    payload = original.get("image")
                    if not isinstance(payload, bytes):
                        raise PhotoExportError(f"Invalid photograph payload: {photo.filename}")
                    with Image.open(io.BytesIO(payload)) as image:
                        image.thumbnail((1800, 1800))
                        image.convert("RGB").save(destination / photo.filename, quality=88, optimize=True)
        except (OSError, ValueError, IndexError) as error:
            raise PhotoExportError(f"Publication photograph export failed: {error}") from error

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    PhotoExporter().export(root / 'sources/inventory/4-II. Murat Külliyesi.pdf', root / 'prototype/assets', (
        Photograph('aerial.jpg', 1, 0), Photograph('courtyard.jpg', 12, 0),
        Photograph('fountain.jpg', 14, 0), Photograph('imaret-front.jpg', 15, 0),
        Photograph('imaret-inside.jpg', 16, 0),
    ))
