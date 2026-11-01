"""Optional text extraction over already verified registered-source bytes."""

from typing import Protocol

from pastport.domain.evidence import Source
from pastport.domain.modules import SourceDocument
from pastport.ports.modules import Cancellation


class SourceTextError(Exception):
    """A bounded extraction failed without changing the registered source identity."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SourceTextExtractor(Protocol):
    @property
    def identity(self) -> str:
        """Versioned implementation and limits, included in source receipt identity."""
        ...

    async def extract(
        self,
        source: Source,
        content: bytes,
        *,
        timeout_seconds: float,
        cancellation: Cancellation,
    ) -> SourceDocument: ...
