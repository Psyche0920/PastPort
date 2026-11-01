"""Mapped document page numbers cannot silently become original-PDF citations."""

from pathlib import Path

from test_story_automation import material_fixture

from pastport.application.source_lineage import (
    OriginalDocumentText,
    OriginalPageText,
    SourceLineageProjector,
)


def test_exact_original_page_projection_preserves_objects_and_reviews(tmp_path: Path) -> None:
    museum = material_fixture(tmp_path / "material").museum
    obj = museum.objects[0]
    assert obj.quote is not None
    projected = SourceLineageProjector().project(
        museum,
        OriginalDocumentText(
            pdf_sha256="b" * 64,
            pages=(
                OriginalPageText(page_index=0, text="Other content"),
                OriginalPageText(page_index=1, text="Prefix\n" + obj.quote.text + "\nSuffix"),
            ),
        ),
    )
    assert projected.snapshot.objects[0].quote.pdf_page == 2
    assert projected.receipt.citations[0].input_page == 1
    assert projected.receipt.citations[0].outcome == "exact_unique_page"
    assert projected.snapshot.objects[0].stable_id == obj.stable_id
    assert projected.snapshot.objects[0].text_review == obj.text_review
    assert projected.snapshot.objects[0].pairing_version == obj.pairing_version
    assert projected.snapshot.metric_spatial is None
    assert projected.snapshot.content_revision != museum.content_revision


def test_ambiguous_or_absent_original_text_is_withheld(tmp_path: Path) -> None:
    museum = material_fixture(tmp_path / "material").museum
    assert museum.objects[0].quote is not None
    quote = museum.objects[0].quote.text
    for pages, expected in (((quote, quote), "ambiguous"), (("unrelated",), "not_found")):
        result = SourceLineageProjector().project(
            museum,
            OriginalDocumentText(
                pdf_sha256="b" * 64,
                pages=tuple(
                    OriginalPageText(page_index=i, text=text) for i, text in enumerate(pages)
                ),
            ),
        )
        assert result.snapshot.objects[0].quote is None
        assert result.receipt.citations[0].outcome == expected
        assert result.receipt.review_states_changed is False


def test_already_registered_original_source_is_not_reaudited_for_ocr(tmp_path: Path) -> None:
    museum = material_fixture(tmp_path / "material").museum
    result = SourceLineageProjector().project(
        museum,
        OriginalDocumentText(
            pdf_sha256=museum.source_pdf_sha256,
            pages=(OriginalPageText(page_index=0, text=""),),
        ),
    )
    assert result.snapshot == museum
    assert result.receipt.citations[0].outcome == "same_source"
