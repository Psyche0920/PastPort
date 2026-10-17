"""Bounded file input for runtime package loading."""

from pathlib import Path
from typing import Protocol


class PackageFileReader(Protocol):
    def read(self, path: Path, maximum_bytes: int) -> bytes: ...
