"""Native source access; IDML selectors never pretend to be printed PDF pages."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal
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


class PDFCandidateSource(CandidateSource):
    filename='source.pdf'
    kind='pdf'

    def __init__(self, upstream: Path, *, content_order: bool = False) -> None:
        super().__init__(upstream)
        self.content_order = content_order

    @property
    def count(self) -> int:
        with self.path.open('rb') as stream:return len(PdfReader(stream,strict=True).pages)

    def text(self, unit: int) -> str:
        options = ['-raw'] if self.content_order else []
        result=subprocess.run(['pdftotext',*options,'-f',str(unit),'-l',str(unit),str(self.path),'-'],
                              check=True,capture_output=True,text=True,timeout=60)
        return result.stdout

    def render(self, unit: int, output: Path) -> None:
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
    return PDFCandidateSource(upstream, content_order=(upstream/'catalog-text-order').is_file())
