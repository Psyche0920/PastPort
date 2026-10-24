"""Transport boundary keeps the SDK outside domain/application services."""

from typing import Protocol

from pastport_evidence.domain.execution import ExecutionInput, ExecutionOutput, SDKReadiness


class SemanticTransport(Protocol):
    def readiness(self, model_id: str) -> SDKReadiness: ...
    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput: ...
