"""Native source access; IDML selectors never pretend to be printed PDF pages."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal
import hashlib
from pydantic import Field, model_validator
from pastport_matched_environment.domain.models import ProjectAssetRef
import shutil
import subprocess
from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader


class SourceUnit(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='forbid')
    unit_id: int
    text: str
    member: str
    story_id: str
    start: int
    paragraph_index: int
    preview: str


class IDMLSourceUnits(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='forbid')
    source_format: Literal["idml"]
    units: tuple[SourceUnit,...]


class CandidateSource(ABC):
    filename: str
    kind: str

    def __init__(self, upstream: Path) -> None:
        self.upstream=upstream

    @property
    def path(self) -> Path:
        return self.upstream/self.filename

    @property
    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def text(self, unit: int) -> str: ...

    @abstractmethod
    def render(self, unit: int, output: Path) -> None: ...


class _SavedPage(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra="ignore")
    page_index: int = Field(ge=0)
    original_text: str


class _SavedPDF(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra="ignore")
    source: ProjectAssetRef
    page_count: int = Field(ge=1,le=500)
    pages: tuple[_SavedPage,...]

    @model_validator(mode="after")
    def complete(self) -> _SavedPDF:
        if tuple(p.page_index for p in self.pages)!=tuple(range(self.page_count)):
            raise ValueError("Saved PDF text must cover every page in order")
        return self


class PDFCandidateSource(CandidateSource):
    filename='source.pdf'
    kind='pdf'

    def __init__(self, upstream: Path, *, content_order: bool = False) -> None:
        super().__init__(upstream)
        self.content_order = content_order
        saved=upstream/'source-text.json'
        self.saved_text=_SavedPDF.model_validate_json(saved.read_bytes()) if saved.is_file() else None
        if self.saved_text is not None:
            with self.path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=self.saved_text.source.asset.sha256:
                    raise ValueError('Saved text belongs to another original PDF')

    @property
    def count(self) -> int:
        if self.saved_text is not None:return self.saved_text.page_count
        with self.path.open('rb') as stream:return len(PdfReader(stream,strict=True).pages)

    def text(self, unit: int) -> str:
        if self.saved_text is not None:return self.saved_text.pages[unit-1].original_text
        options = ['-raw'] if self.content_order else []
        result=subprocess.run(['pdftotext',*options,'-f',str(unit),'-l',str(unit),str(self.path),'-'],
                              check=True,capture_output=True,text=True,timeout=60)
        return result.stdout

    def render(self, unit: int, output: Path) -> None:
        if self.saved_text is not None:raise ValueError('Text-first source pages must not be rendered')
        subprocess.run(['pdftoppm','-f',str(unit),'-l',str(unit),'-singlefile','-scale-to','1400',
                        '-png',str(self.path),str(output.with_suffix(''))],
                       check=True,capture_output=True,timeout=60)


class IDMLCandidateSource(CandidateSource):
    filename='source.idml'
    kind='idml'

    def __init__(self, upstream: Path) -> None:
        super().__init__(upstream)
        self.document=IDMLSourceUnits.model_validate_json((upstream/'source-units.json').read_bytes())
        if self.document.source_format!='idml':raise ValueError('Invalid native source format')
        self.units={u.unit_id:u for u in self.document.units}
        if len(self.units)!=len(self.document.units) or sorted(self.units)!=list(range(1,len(self.units)+1)):
            raise ValueError('IDML source units must be uniquely and completely indexed')

    @property
    def count(self) -> int:return len(self.units)

    def text(self, unit: int) -> str:return self.units[unit].text

    def render(self, unit: int, output: Path) -> None:
        source=(self.upstream/self.units[unit].preview).resolve()
        if not source.is_relative_to(self.upstream.resolve()) or source.is_symlink():
            raise ValueError('IDML source preview leaves registered input')
        shutil.copyfile(source,output)


def candidate_source(upstream: Path) -> CandidateSource:
    if (upstream/'source-units.json').is_file():return IDMLCandidateSource(upstream)
    # Historical saved handoffs pin this extraction order; new PDF jobs do not write it.
    return PDFCandidateSource(upstream, content_order=(upstream/'catalog-text-order').is_file())
