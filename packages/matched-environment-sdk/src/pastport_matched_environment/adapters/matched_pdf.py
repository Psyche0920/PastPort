"""Read optional internal evidence links from a supplied matched PDF, never scripts."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from pastport_matched_environment.domain.environment import MatchedPDFIndex, PageCrop, PDFIndexEntry
from pastport_matched_environment.domain.pdf import RegisteredPDF


class MatchedPDFIndexReader:
    """An unrecognized or ambiguous layout falls back to full page inspection."""

    def read(self, path: Path, document: RegisteredPDF) -> MatchedPDFIndex:
        empty = MatchedPDFIndex(entries=(), basis="No complete supported internal evidence index")
        with path.open("rb") as source:
            reader = PdfReader(source)
            if len(reader.pages) != document.page_count:
                raise ValueError("PDF index and registered document disagree")
            page_ids = {
                page.indirect_reference.idnum: i + 1
                for i, page in enumerate(reader.pages)
                if page.indirect_reference
            }
            links: list[tuple[int, int, tuple[float, float, float, float]]] = []
            for number, page in enumerate(reader.pages, 1):
                if page.rotation != 0:
                    return empty
                for reference in page.get("/Annots", ()):
                    annotation = reference.get_object()
                    if not isinstance(annotation, DictionaryObject):
                        continue
                    destination = annotation.get("/Dest")
                    if not isinstance(destination, ArrayObject) or not destination:
                        continue
                    target = destination[0]
                    rectangle = annotation.get("/Rect")
                    if (
                        not isinstance(target, IndirectObject)
                        or target.idnum not in page_ids
                        or not isinstance(rectangle, ArrayObject)
                        or len(rectangle) != 4
                    ):
                        return empty
                    coords = tuple(float(value) for value in rectangle)
                    links.append(
                        (
                            number,
                            page_ids[target.idnum],
                            (coords[0], coords[1], coords[2], coords[3]),
                        )
                    )
            if not links:
                return empty
            headers: dict[int, tuple[int, str]] = {}
            for target in {link[1] for link in links}:
                page_text = document.pages[target - 1].original_text
                match = re.match(r"\s*(\d+)\s*(?:→|➜|->)\s*([A-Za-z][A-Za-z0-9._:-]*)", page_text)
                if match is None:
                    continue
                headers[target] = (int(match.group(1)), match.group(2))
            if not headers:
                return empty
            entries: dict[int, PDFIndexEntry] = {}
            observations: dict[int, list[PageCrop]] = {}
            for target, (number, history_key) in headers.items():
                if number in entries:
                    return empty
                entries[number] = PDFIndexEntry(
                    number=number, history_key=history_key, detail_page=target, modern_images=()
                )
                observations[number] = []
            for page_number, target, (x0, y0, x1, y1) in links:
                if target not in headers:
                    continue
                registered = document.pages[page_number - 1]
                top, bottom = registered.page_height - y1, registered.page_height - y0
                # Card-sized links span text and thumbnails; only links fully inside
                # a registered embedded image represent a photographic observation.
                inside = any(
                    x0 >= im.region.x0 - 1
                    and x1 <= im.region.x1 + 1
                    and top >= im.region.top - 1
                    and bottom <= im.region.bottom + 1
                    for im in registered.image_regions
                )
                if not inside:
                    continue
                box = (
                    x0 / registered.page_width,
                    top / registered.page_height,
                    x1 / registered.page_width,
                    bottom / registered.page_height,
                )
                if not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
                    return empty
                number = headers[target][0]
                crop = PageCrop(
                    page=page_number,
                    box=box,
                    basis=(
                        "Photographic selection linked by this PDF to its numbered evidence entry; "
                        "identity remains reviewable"
                    ),
                )
                if crop not in observations[number]:
                    observations[number].append(crop)
            if any(not items for items in observations.values()):
                return empty
            return MatchedPDFIndex(
                entries=tuple(
                    entry.model_copy(update={"modern_images": tuple(observations[number])})
                    for number, entry in sorted(entries.items())
                ),
                basis=(
                    "Internal links and photographic rectangles in this matched PDF; "
                    "no VR positions or prior outputs used"
                ),
            )
