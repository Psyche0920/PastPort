"""Transport boundary keeps the SDK outside domain/application services."""

from pathlib import Path
from typing import Protocol

from pastport_pdf_vr.domain.animation import AnimationCapabilities
from pastport_pdf_vr.domain.execution import ExecutionInput, ExecutionOutput, SDKReadiness


class SemanticTransport(Protocol):
    def readiness(self, model_id: str) -> SDKReadiness: ...
    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput: ...


class ImageTransport(SemanticTransport, Protocol):
    def capabilities(self, model_id: str, directory: Path) -> AnimationCapabilities: ...
