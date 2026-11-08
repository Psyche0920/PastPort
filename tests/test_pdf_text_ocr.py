"""Text-first ingestion preserves every page and only renders OCR candidates."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.ocr import TesseractPageOCR
from pastport_evidence.adapters.pdf import PDFProcessingError, PopplerPDFReader
from pastport_evidence.application.evidence import CorpusIndex, EvidenceValidationError
from pastport_evidence.application.pdf_ingestion import PDFIngestionService
from pastport_evidence.domain.models import ProcessingLimits
from pastport_evidence.domain.pdf import (
    PDFExtractionStatus,
    PDFRegion,
    PDFTextLine,
    RegisteredPDF,
)
from pastport_evidence.ports.ocr import OCRError, OCRResult
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


class FakeOCR:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def recognize(
        self, image: bytes, page_width: float, page_height: float, timeout_seconds: int
    ) -> OCRResult:
        self.calls += 1
        if self.fail:
            raise OCRError("OCR_REQUIRED: engine unavailable")
        line = PDFTextLine(
            line_index=0,
            text="Recovered scan text.",
            normalized_text="Recovered scan text.",
            region=PDFRegion(x0=10.0, top=10.0, x1=100.0, bottom=30.0),
        )
        return OCRResult((line,), "fake-ocr", "eng", 96.0)


class CountingReader(PopplerPDFReader):
    def __init__(self, executable: Path, ocr: FakeOCR | TesseractPageOCR) -> None:
        super().__init__(executable, ocr=ocr)
        self.rendered: list[int] = []

    def _render_page(
        self,
        pdf_path: Path,
        page_index: int,
        max_render_edge: int,
        max_render_bytes: int,
        timeout_seconds: int,
    ) -> bytes:
        self.rendered.append(page_index)
        return super()._render_page(
            pdf_path, page_index, max_render_edge, max_render_bytes, timeout_seconds
        )


def mixed_pdf(path: Path) -> None:
    canvas = Canvas(str(path), pagesize=(600, 400), invariant=1)
    canvas.drawString(40, 350, "Native first line of the historical source.")
    canvas.drawString(40, 325, "Native second line for source citation.")
    canvas.showPage()
    with Image.new("RGB", (1800, 1200), "white") as image:
        draw = ImageDraw.Draw(image)
        font = (
            ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 64)
            if Path("/System/Library/Fonts/Supplemental/Arial.ttf").exists()
            else ImageFont.load_default(size=64)
        )
        draw.text((100, 150), "Scanned source passage.", font=font, fill="black")
        canvas.drawImage(ImageReader(image), 0, 0, width=600, height=400)
    canvas.showPage()
    canvas.showPage()  # A genuinely blank page is preserved without OCR/rendering.
    canvas.save()


def executable() -> Path:
    value = shutil.which("pdftoppm")
    if value is None:
        pytest.skip("Poppler required")
    return Path(value)


@pytest.mark.parametrize("garbled", [False, True])
def test_only_scan_or_garbled_pages_render_and_all_lines_stay_located(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    garbled: bool,
) -> None:
    pdf = tmp_path / "original.pdf"
    mixed_pdf(pdf)
    original = pdf.read_bytes()
    if garbled:
        from pdfplumber.page import Page

        original_extract = Page.extract_text

        def extract(page: Page, **kwargs: object) -> str:
            return (
                "\ufffd\ufffd(cid:12)"
                if page.page_number == 1
                else original_extract(page, **kwargs)
            )

        monkeypatch.setattr(Page, "extract_text", extract)
    ocr = FakeOCR()
    reader = CountingReader(executable(), ocr)
    registered = PDFIngestionService(
        LocalAssetStore(tmp_path / "assets"), reader
    ).register_and_extract("test", pdf, ProcessingLimits())
    assert reader.rendered == ([0, 1] if garbled else [1])
    assert ocr.calls == len(reader.rendered)
    assert pdf.read_bytes() == original
    assert registered.page_count == 3
    assert registered.pages[2].extraction_status == PDFExtractionStatus.EMPTY_PAGE
    assert all(page.rendered_page is None for page in registered.pages)
    assert registered.pages[1].ocr_reason == "no_text"
    assert registered.pages[1].ocr_engine == "fake-ocr"
    if garbled:
        assert registered.pages[0].native_text == "\ufffd\ufffd(cid:12)"
        assert registered.pages[0].ocr_reason == "garbled"
    corpus = CorpusIndex(registered, passage_characters=100)
    assert corpus.passages
    for passage in corpus.passages:
        corpus.validate_passage(passage)
        page = registered.pages[passage.page_index]
        assert passage.line_start is not None and passage.line_end is not None
        assert passage.quote in "\n".join(
            page.original_text.splitlines()[passage.line_start - 1 : passage.line_end]
        )
    bad = corpus.passages[0].model_copy(update={"line_start": 100, "line_end": 100})
    with pytest.raises(EvidenceValidationError, match="line selectors"):
        corpus.validate_passage(bad)
    assert RegisteredPDF.model_validate_json(registered.model_dump_json()) == registered


def test_missing_ocr_fails_with_page_number_instead_of_ignoring_scan(tmp_path: Path) -> None:
    pdf = tmp_path / "original.pdf"
    mixed_pdf(pdf)
    reader = CountingReader(executable(), FakeOCR(fail=True))
    with pytest.raises(PDFProcessingError, match="page 2: OCR_REQUIRED"):
        PDFIngestionService(LocalAssetStore(tmp_path / "assets"), reader).register_and_extract(
            "test", pdf, ProcessingLimits()
        )
    assert reader.rendered == [1]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Readable 中文 English Türkçe", None),
        ("", "no_text"),
        ("\ufffdText", "garbled"),
        ("(cid:87) (cid:90)", "garbled"),
        ("\ue001\ue002", "garbled"),
    ],
)
def test_garble_detection_does_not_treat_non_latin_languages_as_corruption(
    text: str, expected: str | None
) -> None:
    assert PopplerPDFReader.ocr_reason(text) == expected


def test_real_local_ocr_and_line_boxes(tmp_path: Path) -> None:
    if shutil.which("tesseract") is None:
        pytest.skip("Local OCR integration requires Tesseract")
    pdf = tmp_path / "original.pdf"
    mixed_pdf(pdf)
    reader = CountingReader(executable(), TesseractPageOCR(languages="eng"))
    document = PDFIngestionService(
        LocalAssetStore(tmp_path / "assets"), reader
    ).register_and_extract("test", pdf, ProcessingLimits())
    assert reader.rendered == [1]
    scan = document.pages[1]
    assert "Scanned source passage" in scan.original_text
    assert scan.extraction_status == PDFExtractionStatus.OCR_EXTRACTED
    assert scan.ocr_confidence is not None and scan.ocr_confidence >= 40
    assert scan.ocr_engine and scan.ocr_engine.startswith("tesseract")
    for line in scan.text_lines:
        assert 0 <= line.region.x0 <= line.region.x1 <= scan.page_width
        assert 0 <= line.region.top <= line.region.bottom <= scan.page_height


def test_text_matching_sends_located_text_without_pdf_page_images(tmp_path: Path) -> None:
    from pastport_evidence.adapters.execution import SubscriptionExecutor
    from pastport_evidence.application.preparation import MappingPreparation
    from pastport_evidence.domain.build import PDFMatchRequest
    from pastport_evidence.domain.execution import (
        ExecutionInput,
        ExecutionOutput,
        SDKReadiness,
        SubscriptionGrant,
    )
    from pastport_evidence.domain.photos import PhotoInventory
    from pastport_evidence.domain.recognition import RecognitionResult, SceneEntity

    class Transport:
        def __init__(self) -> None:
            self.requests: list[ExecutionInput] = []

        def readiness(self, model_id: str) -> SDKReadiness:
            return SDKReadiness(authenticated=True, auth_mode="chatgpt", requested_model=model_id, model_available=True, image_input_supported=True)

        def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
            self.requests.append(request)
            return ExecutionOutput(
                payload_json='{"matches":[],"gaps":["no supported match in fixture"]}',
                receipt_ref="test-receipt",
                thread_ref="test-thread",
                turn_ref="test-turn",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )

    pdf = tmp_path / "original.pdf"
    mixed_pdf(pdf)
    from pypdf import PdfReader, PdfWriter

    original = PdfReader(pdf)
    expanded = PdfWriter()
    for page in original.pages:
        expanded.add_page(page)
    for _ in range(3):
        expanded.add_page(original.pages[0])
    expanded.write(tmp_path / "six-pages.pdf")
    pdf = tmp_path / "six-pages.pdf"
    assets = LocalAssetStore(tmp_path / "assets")
    document = PDFIngestionService(
        assets, CountingReader(executable(), FakeOCR())
    ).register_and_extract("test", pdf, ProcessingLimits())
    artifacts = tmp_path / "run"
    artifacts.mkdir()
    entity = SceneEntity(
        object_id="test-object",
        display_number=1,
        label="Stone stair",
        category="stair",
        distinguishing_features=("Stone steps",),
    )
    for name, value in (
        ("pdf.json", document),
        ("recognition.json", RecognitionResult(entities=(entity,), calls_used=0, gaps=())),
        ("photo-inventory.json", PhotoInventory(photos=())),
    ):
        (artifacts / name).write_text(value.model_dump_json())
    transport = Transport()
    grant = SubscriptionGrant(project_id="test", grant_ref="test-grant")
    executor = SubscriptionExecutor(tmp_path / "executions.sqlite3", grant, transport)
    service = MappingPreparation(
        tmp_path,
        artifacts,
        grant,
        "demo_substitution",
        "test",
        assets,
        executor,
        mapping_prompt_version="text-v1",
    )
    service.map_pdf()
    assert len(transport.requests) == 1
    request = PDFMatchRequest.model_validate_json(transport.requests[0].payload_json)
    assert len(request.pages) == 6
    assert all(page.image is None for page in request.pages)
    assert all(
        passage.line_start is not None for page in request.pages for passage in page.passages
    )
    assert request.reference_sheets
    assert transport.requests[0].image_hashes == tuple(
        sheet.image.asset.sha256 for sheet in request.reference_sheets
    )
    service.map_pdf()
    assert len(transport.requests) == 1  # No new model request for a completed stage.


def test_existing_visual_prompt_policy_is_not_replaced(tmp_path: Path) -> None:
    from pastport_evidence.application.prompting import resolve_prompt_profile

    (tmp_path / "semantic-policy.json").write_text('{"photo":"v3","mapping":"v3","evidence":"v3"}')
    assert resolve_prompt_profile(tmp_path).mapping == "v3"


def test_delivery_preserves_original_pdf_and_all_page_line_records(tmp_path: Path) -> None:
    import json

    from pastport_evidence.application.document_package import DocumentPackageExporter
    from pastport_evidence.application.photo_mapping import PreparedDocuments
    from pastport_evidence.domain.photos import PhotoInventory

    pdf = tmp_path / "original.pdf"
    mixed_pdf(pdf)
    assets = LocalAssetStore(tmp_path / "assets")
    source = PDFIngestionService(
        assets, CountingReader(executable(), FakeOCR())
    ).register_and_extract(
        "test",
        pdf,
        ProcessingLimits(),
    )
    bundle = PreparedDocuments(
        project_id="test",
        input_binding="fixture",
        source=source.source,
        inventory=PhotoInventory(photos=()),
        objects=(),
        gaps=(),
    )
    exporter = DocumentPackageExporter(assets)
    target = exporter.write(tmp_path / "delivery", bundle, source)
    assert (target / "source.pdf").read_bytes() == pdf.read_bytes()
    record = json.loads((target / "source-text.json").read_text())
    assert record["original_filename"] == "original.pdf"
    assert len(record["pages"]) == 3
    assert record["pages"][1]["ocr_engine"] == "fake-ocr"
    assert record["pages"][0]["text_lines"][0]["line_index"] == 0
    assert all(page["rendered_page"] is None for page in record["pages"])
    assert exporter.write(tmp_path / "delivery", bundle, source) == target
    exporter.validate(target)


def test_native_text_does_not_require_render_or_ocr_binaries(tmp_path: Path) -> None:
    pdf = tmp_path / "native.pdf"
    canvas = Canvas(str(pdf), pagesize=(600, 400), invariant=1)
    canvas.drawString(40, 350, "Native text without any image dependency.")
    canvas.save()
    ocr = FakeOCR(fail=True)
    reader = CountingReader(tmp_path / "missing-poppler", ocr)
    document = PDFIngestionService(
        LocalAssetStore(tmp_path / "assets"), reader
    ).register_and_extract(
        "test",
        pdf,
        ProcessingLimits(),
    )
    assert reader.rendered == [] and ocr.calls == 0
    assert document.pages[0].original_text == "Native text without any image dependency."
