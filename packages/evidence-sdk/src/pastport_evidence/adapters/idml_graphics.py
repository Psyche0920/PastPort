"""Resolve only explicitly supplied local graphics; never follow source-document URIs."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path, PurePosixPath
import stat
from typing import BinaryIO, cast
import unicodedata
import warnings
from zipfile import ZipFile
from PIL import Image, ImageOps, UnidentifiedImageError


class IDMLGraphicError(ValueError):
    """A supplied graphic library exceeds its declared local input profile."""


@dataclass(frozen=True, slots=True)
class IDMLGraphicSource:
    path: Path
    member: str | None
    size: int

    @contextmanager
    def open(self) -> Iterator[BinaryIO]:
        if self.member is None:
            with self.path.open('rb') as stream:
                yield stream
        else:
            with ZipFile(self.path) as archive, archive.open(self.member) as stream:
                yield cast(BinaryIO, stream)

    def digest(self) -> str:
        digest=hashlib.sha256()
        with self.open() as stream:
            for block in iter(lambda: stream.read(1024**2), b''):
                digest.update(block)
        return digest.hexdigest()

    def thumbnail(self, output: Path, edge: int = 1280) -> None:
        if not 256 <= edge <= 2048:
            raise IDMLGraphicError('Invalid preview resolution')
        try:
            with self.open() as stream:
                content=stream.read(128*1024**2+1)
            if len(content)>128*1024**2:
                raise IDMLGraphicError('Image exceeds bounded read profile')
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as raw:
                    if raw.width*raw.height>80_000_000:
                        raise IDMLGraphicError('Image exceeds 80 megapixels')
                    raw.draft('RGB',(edge,edge))
                    with ImageOps.exif_transpose(raw) as upright:
                        upright.thumbnail((edge,edge))
                        with upright.convert('RGB') as rgb:
                            rgb.save(output,'JPEG',quality=88)
        except (UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError, OSError) as error:
            raise IDMLGraphicError('Unable to decode linked graphic') from error


class IDMLGraphicLibrary:
    """Index a folder or large ZIP without extracting the original collection."""

    def __init__(self, supplied: Path | None) -> None:
        self.entries: dict[str,tuple[IDMLGraphicSource,...]]={}
        if supplied is None:
            return
        if supplied.is_symlink():
            raise IDMLGraphicError('Linked library paths are not accepted')
        if supplied.is_dir():
            self._folder(supplied)
        elif supplied.is_file() and supplied.suffix.lower()=='.zip':
            self._archive(supplied)
        else:
            raise IDMLGraphicError('Supply a local graphics directory or ZIP')

    def _add(self, name: str, source: IDMLGraphicSource) -> None:
        if source.size>128*1024**2:
            raise IDMLGraphicError('Individual linked graphic exceeds 128 MiB')
        normalized=unicodedata.normalize('NFC',name)
        self.entries[normalized]=self.entries.get(normalized,())+(source,)

    def _folder(self, root: Path) -> None:
        total=0
        for index,path in enumerate(root.rglob('*')):
            if index>=5000 or path.is_symlink():
                raise IDMLGraphicError('Unsafe or oversized graphic library')
            if path.is_file():
                size=path.stat().st_size;total+=size
                self._add(path.name,IDMLGraphicSource(path,None,size))
        if total>4*1024**3:
            raise IDMLGraphicError('Graphics exceed four GiB')

    def _archive(self, source: Path) -> None:
        if source.stat().st_size>3*1024**3:
            raise IDMLGraphicError('Graphics ZIP exceeds three GiB')
        with ZipFile(source) as archive:
            entries=archive.infolist()
            if len(entries)>5000 or sum(e.file_size for e in entries)>4*1024**3:
                raise IDMLGraphicError('Expanded graphics exceed bounded profile')
            seen=set()
            for entry in entries:
                p=PurePosixPath(entry.filename)
                if (p.is_absolute() or '..' in p.parts or '\\' in entry.filename
                    or entry.filename in seen or stat.S_ISLNK(entry.external_attr>>16)
                    or entry.flag_bits&1):
                    raise IDMLGraphicError('Unsafe or duplicate graphics archive member')
                seen.add(entry.filename)
                if entry.file_size>max(1024**2,entry.compress_size*500):
                    raise IDMLGraphicError('Graphic expansion ratio exceeds profile')
                if not entry.is_dir() and '__MACOSX' not in p.parts and not p.name.startswith('.'):
                    self._add(p.name,IDMLGraphicSource(source,entry.filename,entry.file_size))
