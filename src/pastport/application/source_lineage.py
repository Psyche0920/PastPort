"""Project mapped-PDF citations onto original pages without changing native reviews."""

import unicodedata
from typing import Literal

from pydantic import Field

from pastport.domain.common import CanonicalSerializer, Contract, Sha256
from pastport.domain.story_inputs import (
    EnvironmentContentRevision,
    EnvironmentObject,
    EnvironmentQuote,
    EnvironmentSnapshot,
)


class OriginalPageText(Contract):
    page_index: int = Field(ge=0)
    text: str


class OriginalDocumentText(Contract):
    pdf_sha256: Sha256
    pages: tuple[OriginalPageText, ...] = Field(min_length=1)


class CitationProjection(Contract):
    object_number: int = Field(ge=1)
    input_page: int | None
    original_page: int | None
    outcome: Literal["same_source", "exact_unique_page", "not_found", "ambiguous", "no_quote"]


class SourceLineageReceipt(Contract):
    native_pdf_sha256: Sha256
    original_pdf_sha256: Sha256
    native_snapshot_sha256: Sha256
    projected_snapshot_sha256: Sha256
    citations: tuple[CitationProjection, ...]
    review_states_changed: Literal[False] = False


class SourceLineageProjection(Contract):
    snapshot: EnvironmentSnapshot
    receipt: SourceLineageReceipt


class SourceLineageProjector:
    @staticmethod
    def normalized(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).split())

    def project(
        self,
        native: EnvironmentSnapshot,
        original: OriginalDocumentText,
    ) -> SourceLineageProjection:
        if tuple(page.page_index for page in original.pages) != tuple(range(len(original.pages))):
            raise ValueError("Original PDF page coverage must be complete and ordered")
        if any(obj.quote and obj.quote.idml_selector is not None for obj in native.objects):
            raise ValueError("IDML citations require native source projection, not PDF page search")
        same_source = native.source_pdf_sha256 == original.pdf_sha256
        pages = tuple(self.normalized(page.text) for page in original.pages)
        objects: list[EnvironmentObject] = []
        citations: list[CitationProjection] = []
        for obj in native.objects:
            quote = obj.quote
            if quote is None:
                objects.append(obj)
                citations.append(
                    CitationProjection(
                        object_number=obj.object_number,
                        input_page=None,
                        original_page=None,
                        outcome="no_quote",
                    )
                )
                continue
            if quote.pdf_page is None:
                raise ValueError("Native IDML selectors cannot use PDF page projection")
            normalized = self.normalized(quote.text)
            matches = tuple(
                index + 1 for index, text in enumerate(pages) if normalized and normalized in text
            )
            page = (
                quote.pdf_page
                if same_source and 1 <= quote.pdf_page <= len(pages)
                else (matches[0] if len(matches) == 1 else None)
            )
            outcome: Literal["same_source", "exact_unique_page", "not_found", "ambiguous"] = (
                "same_source"
                if page is not None and same_source
                else "exact_unique_page"
                if page is not None
                else "ambiguous"
                if matches
                else "not_found"
            )
            objects.append(
                obj.model_copy(
                    update={
                        "quote": EnvironmentQuote(text=quote.text, pdf_page=page)
                        if page is not None
                        else None
                    }
                )
            )
            citations.append(
                CitationProjection(
                    object_number=obj.object_number,
                    input_page=quote.pdf_page,
                    original_page=page,
                    outcome=outcome,
                )
            )
        content_revision = CanonicalSerializer.digest(
            EnvironmentContentRevision(objects=tuple(objects))
        )
        changed = content_revision != native.content_revision or not same_source
        projected = EnvironmentSnapshot.model_validate(
            native.model_dump()
            | {
                "objects": tuple(objects),
                "content_revision": content_revision,
                "source_pdf_sha256": original.pdf_sha256,
                # Content-bound geometry must be recomputed against the derived content revision.
                "metric_spatial": None if changed else native.metric_spatial,
                "spatial_profile": "panorama_positions_only" if changed else native.spatial_profile,
                "issues": native.issues
                + (
                    (
                        "Original-PDF citations were projected by exact text; missing or ambiguous "
                        "citations were withheld. Native review and identity states were preserved.",
                    )
                    if changed
                    else ()
                ),
            }
        )
        return SourceLineageProjection(
            snapshot=projected,
            receipt=SourceLineageReceipt(
                native_pdf_sha256=native.source_pdf_sha256,
                original_pdf_sha256=original.pdf_sha256,
                native_snapshot_sha256=CanonicalSerializer.digest(native),
                projected_snapshot_sha256=CanonicalSerializer.digest(projected),
                citations=tuple(citations),
            ),
        )
