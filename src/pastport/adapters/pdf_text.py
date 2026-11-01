"""Optional pypdf extraction in a disposable process with explicit resource limits."""

import asyncio
import importlib
import io
import math
import os
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, ConfigDict, ValidationError

from pastport.domain.common import SourceLocator
from pastport.domain.evidence import Source
from pastport.domain.modules import LocatedText, SourceDocument
from pastport.ports.modules import Cancellation
from pastport.ports.source_text import SourceTextError


class _Pages(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    pages: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PdfTextExtractor:
    """Keep untrusted PDF parsing killable; no provider or authoring SDK is imported."""

    maximum_pages: int = 200
    maximum_characters: int = 500000
    maximum_seconds: float = 20.0

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_pages <= 2000:
            raise ValueError("PDF page limit must be between 1 and 2000")
        if not 1 <= self.maximum_characters <= 2000000:
            raise ValueError("PDF text limit must be between 1 and 2000000")
        if not 0 < self.maximum_seconds <= 120 or not math.isfinite(self.maximum_seconds):
            raise ValueError("PDF timeout must be finite and between 0 and 120 seconds")

    @property
    def identity(self) -> str:
        try:
            parser_version = version("pypdf")
        except PackageNotFoundError:
            parser_version = "unavailable"
        return (
            f"pypdf-text-v1:parser={parser_version}:pages={self.maximum_pages}:chars={self.maximum_characters}"
            f":seconds={self.maximum_seconds}"
        )

    async def extract(
        self,
        source: Source,
        content: bytes,
        *,
        timeout_seconds: float,
        cancellation: Cancellation,
    ) -> SourceDocument:
        cancellation.raise_if_cancelled()
        if not content.startswith(b"%PDF"):
            raise SourceTextError("PDF_INVALID", "Registered PDF has no PDF header")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise SourceTextError("PDF_TIMEOUT", "PDF extraction deadline has expired")
        timeout = min(timeout_seconds, self.maximum_seconds)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(Path(__file__).resolve().parents[2]), environment.get("PYTHONPATH", ""))
        )
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pastport.adapters.pdf_text",
                str(self.maximum_pages),
                str(self.maximum_characters),
                str(math.ceil(timeout)),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
            )
        except OSError as error:
            raise SourceTextError("PDF_WORKER_UNAVAILABLE", "Cannot start PDF parser") from error
        communication = asyncio.create_task(process.communicate(content))
        deadline = monotonic() + timeout
        try:
            while not communication.done():
                cancellation.raise_if_cancelled()
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise SourceTextError("PDF_TIMEOUT", "PDF extraction exceeded its deadline")
                await asyncio.wait((communication,), timeout=min(0.05, remaining))
            cancellation.raise_if_cancelled()
            output, _ = communication.result()
            if process.returncode != 0:
                raise SourceTextError("PDF_PARSE_FAILED", "PDF parser failed or exceeded limits")
            try:
                result = _Pages.model_validate_json(output)
            except ValidationError as error:
                raise SourceTextError("PDF_PARSE_FAILED", "Invalid PDF parser result") from error
            if result.error is not None:
                raise SourceTextError(result.error, "PDF extraction failed: " + result.error)
            fragments = tuple(
                LocatedText(
                    locator=SourceLocator(
                        source_id=source.source_id,
                        source_version=source.version,
                        file_sha256=source.file_sha256,
                        page_index=index,
                        printed_page=None,
                        paragraph_or_region=f"pdf-text-offset-{offset}",
                    ),
                    text=text[offset : offset + 10000],
                )
                for index, text in enumerate(result.pages)
                for offset in range(0, len(text), 10000)
                if text[offset : offset + 10000].strip()
            )
            return SourceDocument(
                source=source,
                fragments=fragments,
                status="read"
                if result.pages and all(text.strip() for text in result.pages)
                else "needs_ocr",
            )
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if not communication.done():
                communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)


def _worker() -> None:
    """Parse only in the child so malformed compression cannot block the event loop."""
    import resource

    maximum_pages, maximum_characters, cpu_seconds = map(int, sys.argv[1:])
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds + 1, cpu_seconds + 1))
    # Address-space limits are effective on Linux; macOS still has the CPU/wall deadline.
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    try:
        pdf = importlib.import_module("pypdf")
    except ModuleNotFoundError:
        print(_Pages(error="PDF_DEPENDENCY_UNAVAILABLE").model_dump_json())
        return
    errors = importlib.import_module("pypdf.errors")
    try:
        reader = pdf.PdfReader(io.BytesIO(sys.stdin.buffer.read()), strict=True)
        if reader.is_encrypted:
            result = _Pages(error="PDF_ENCRYPTED")
        elif len(reader.pages) > maximum_pages:
            result = _Pages(error="PDF_PAGE_LIMIT")
        else:
            pages: list[str] = []
            size = 0
            for page in reader.pages:
                text = str(page.extract_text() or "")
                size += len(text)
                if size > maximum_characters:
                    print(_Pages(error="PDF_TEXT_LIMIT").model_dump_json())
                    return
                pages.append(text)
            result = _Pages(pages=tuple(pages))
    except (errors.PyPdfError, ValueError, TypeError, KeyError, IndexError, OSError):
        result = _Pages(error="PDF_INVALID")
    print(result.model_dump_json())


if __name__ == "__main__":
    _worker()
