"""PDF extraction stays optional, located, bounded and inside the shared read ledger."""

import asyncio
import hashlib
import importlib
import io
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from pastport.adapters.pdf_text import PdfTextExtractor
from pastport.application.execution_models import ExecutionSettings
from pastport.application.models import ServiceError
from pastport.application.source_tools import SharedSourceReader
from pastport.application.updates import updated
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.evidence import Source, SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import (
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    ResearchRequest,
    SourceDocument,
)
from pastport.domain.resources import ResourceData, ResourceReference
from pastport.ports.modules import ExecutionContext
from pastport.ports.source_text import SourceTextError


class NotCancelled:
    def raise_if_cancelled(self) -> None:
        pass


def source(content: bytes) -> Source:
    return Source(
        source_id="registered-pdf",
        version="v1",
        file_sha256=hashlib.sha256(content).hexdigest(),
        origin="official",
        title="Registered PDF",
        uri="registered.pdf",
        acquisition_state="downloaded",
        extraction_state="needs_ocr",
    )


def pdf_bytes(pages: tuple[str, ...], *, encrypted: bool = False) -> bytes:
    pytest.importorskip("pypdf")
    pdf = importlib.import_module("pypdf")
    generic = importlib.import_module("pypdf.generic")
    writer = pdf.PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=300, height=300)
        if text:
            font = generic.DictionaryObject(
                {
                    generic.NameObject("/Type"): generic.NameObject("/Font"),
                    generic.NameObject("/Subtype"): generic.NameObject("/Type1"),
                    generic.NameObject("/BaseFont"): generic.NameObject("/Helvetica"),
                }
            )
            page[generic.NameObject("/Resources")] = generic.DictionaryObject(
                {
                    generic.NameObject("/Font"): generic.DictionaryObject(
                        {generic.NameObject("/F1"): font}
                    )
                }
            )
            stream = generic.DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 10 20 Td ({text}) Tj ET".encode("ascii"))
            page[generic.NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("private-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def extract(content: bytes, extractor: PdfTextExtractor | None = None) -> SourceDocument:
    return asyncio.run(
        (extractor or PdfTextExtractor()).extract(
            source(content), content, timeout_seconds=10, cancellation=NotCancelled()
        )
    )


@pytest.mark.parametrize(
    "pages,status,indexes",
    [
        (("First original page", "Second page"), "read", [0, 1]),
        (("", ""), "needs_ocr", []),
        (("First page", "", "Third page"), "needs_ocr", [0, 2]),
    ],
)
def test_original_pdf_pages_survive_partial_ocr(
    pages: tuple[str, ...], status: str, indexes: list[int]
) -> None:
    content = pdf_bytes(pages)
    document = extract(content)
    assert document.source == source(content)
    assert document.status == status
    assert [fragment.locator.page_index for fragment in document.fragments] == indexes
    assert [fragment.text.strip() for fragment in document.fragments] == [p for p in pages if p]
    assert all(
        fragment.locator.file_sha256 == source(content).file_sha256
        and fragment.locator.printed_page is None
        for fragment in document.fragments
    )


@pytest.mark.parametrize(
    "kind,code",
    [
        ("invalid", "PDF_INVALID"),
        ("encrypted", "PDF_ENCRYPTED"),
        ("pages", "PDF_PAGE_LIMIT"),
        ("text", "PDF_TEXT_LIMIT"),
    ],
)
def test_pdf_failures_are_explicit(kind: str, code: str) -> None:
    content = (
        b"%PDF-invalid"
        if kind == "invalid"
        else pdf_bytes(("Extractable text", "Second page"), encrypted=kind == "encrypted")
    )
    extractor = PdfTextExtractor(
        maximum_pages=1 if kind == "pages" else 200,
        maximum_characters=2 if kind == "text" else 500000,
    )
    with pytest.raises(SourceTextError) as failure:
        extract(content, extractor)
    assert failure.value.code == code


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_cancellation_reap_the_parser(
    monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    original = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def slow_worker(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        # Keep real pipes/process cleanup while replacing only the parser's workload.
        child = await original(
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        children.append(child)
        return child

    class CancelDuringParse:
        calls = 0

        def raise_if_cancelled(self) -> None:
            self.calls += 1
            if cancel and self.calls > 2:
                raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_worker)

    async def run() -> None:
        with pytest.raises(asyncio.CancelledError if cancel else SourceTextError) as failure:
            await PdfTextExtractor().extract(
                source(b"%PDF"),
                b"%PDF",
                timeout_seconds=0.15,
                cancellation=CancelDuringParse(),
            )
        if not cancel:
            assert isinstance(failure.value, SourceTextError)
            assert failure.value.code == "PDF_TIMEOUT"
        assert children and children[0].returncode is not None

    asyncio.run(run())


def test_missing_optional_dependency_has_explicit_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pastport.adapters.pdf_text import _worker

    original = importlib.import_module

    def missing(name: str, package: str | None = None) -> object:
        if name == "pypdf":
            raise ModuleNotFoundError("pypdf")
        return original(name, package)

    monkeypatch.setattr(sys, "argv", ["worker", "10", "1000", "10"])
    monkeypatch.setattr(importlib, "import_module", missing)
    # Do not change the test runner's own resource limits; the real child applies them.
    import resource

    monkeypatch.setattr(resource, "setrlimit", lambda *args: None)
    _worker()
    assert '"error":"PDF_DEPENDENCY_UNAVAILABLE"' in capsys.readouterr().out


def test_injected_pdf_reader_uses_graph_permissions_cache_and_receipts(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from test_service import confirm_direction, headers, settings
    from test_shared_execution import SKILLS, GatewayEvidence, start
    from test_workflow_branches import stopped

    from pastport.api.app import create_app

    content = pdf_bytes(("Registered page", ""))
    digest = hashlib.sha256(content).hexdigest()
    observed: list[SourceDocument] = []

    class Resource:
        reads = 0

        def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
            self.reads += 1
            return ResourceData(reference, content, "application/octet-stream")

    resource = Resource()

    class InspectSource(GatewayEvidence):
        async def inventory(
            self, request: InventoryRequest, context: ExecutionContext
        ) -> ModuleResult[SourceManifestDraft]:
            result = await super().inventory(request, context)
            assert result.payload is not None
            return updated(
                result,
                payload=updated(
                    result.payload,
                    sources=tuple(updated(s, file_sha256=digest) for s in result.payload.sources),
                ),
            )

        async def index(
            self, request: IndexRequest, context: ExecutionContext
        ) -> ModuleResult[SourceIndexDraft]:
            result = await super().index(request, context)
            assert result.payload is not None
            return updated(
                result,
                payload=updated(
                    result.payload,
                    sources=tuple(updated(s, file_sha256=digest) for s in result.payload.sources),
                ),
            )

        async def research(
            self, request: ResearchRequest, context: ExecutionContext
        ) -> ModuleResult[EvidenceFindings]:
            registered = request.index.sources[0]
            reference = ArtifactRef(
                artifact_id=registered.source_id,
                project_id=context.metadata.project_id,
                kind="source",
                schema_version="0.1.0",
                content_version=registered.version,
                sha256=registered.file_sha256,
            )
            # A forged source is rejected before any resource/extractor work.
            with pytest.raises(ServiceError, match="not registered"):
                await self.services.sources.read(updated(reference, artifact_id="forged"), context)
            sources = self.services.sources
            assert isinstance(sources, SharedSourceReader)
            default = SharedSourceReader(sources.guard, resource)
            default_operation = default.operation(reference, context)
            assert default_operation != sources.operation(reference, context)
            assert default_operation[1] == CanonicalSerializer.digest(reference)
            legacy = await default.read(reference, context)
            assert legacy.status == "needs_ocr" and not legacy.fragments
            result = await sources.read(reference, context)
            assert result == await sources.read(reference, context)
            observed.append(result)
            return ModuleResult[EvidenceFindings](
                outcome="blocked",
                payload=None,
                issues=(),
                changed_ids=(),
                evidence_requests=(),
                reason="PDF read probe complete",
            )

    config = replace(
        settings(tmp_path),
        execution=ExecutionSettings(allowed_tools=("read_source",)),
        skill_directory=SKILLS,
    )
    with TestClient(
        create_app(
            config,
            resources=resource,
            source_text_extractor=PdfTextExtractor(),
            evidence_factory=InspectSource,
        )
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        stopped(client, run_id, "blocked")
        assert len(observed) == 1
        assert observed[0].status == "needs_ocr"
        assert observed[0].fragments[0].text.strip() == "Registered page"
        assert observed[0].fragments[0].locator.page_index == 0
        assert resource.reads == 2  # legacy and versioned extractor each fetched exactly once
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert budget["used"]["fetch_requests"] == 2
        assert not any(budget["held"].values())


def test_pdf_byte_budget_can_be_explicit_without_changing_default() -> None:
    assert ExecutionSettings().maximum_source_bytes == 262144
    assert (
        ExecutionSettings(maximum_source_bytes=8 * 1024 * 1024).maximum_source_bytes
        == 8 * 1024 * 1024
    )
    with pytest.raises(ValidationError):
        ExecutionSettings(maximum_source_bytes=64 * 1024 * 1024 + 1)
