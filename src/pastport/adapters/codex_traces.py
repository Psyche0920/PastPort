"""Private local invocation evidence, separate from authoritative budget settlement."""

import os
from pathlib import Path
from typing import Literal

from pastport.application.execution_models import ProviderResponse
from pastport.application.models import ServiceError
from pastport.domain.common import Contract, Sha256, Text


class CodexInvocation(Contract):
    request_key: Sha256
    model: Text
    state: Literal["starting", "thread_started", "turn_started", "completed", "outcome_unknown"]
    thread_id: Text | None = None
    turn_id: Text | None = None
    response: ProviderResponse | None = None


class CodexTraceStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, invocation: CodexInvocation) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self.directory / (invocation.request_key + ".json")
            temporary = path.with_suffix(".tmp")
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(invocation.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        except OSError as error:
            raise ServiceError(
                "CODEX_TRACE_UNAVAILABLE", "Cannot persist local invocation evidence"
            ) from error

    def read(self, request_key: str) -> CodexInvocation | None:
        # Validate the path component before filesystem access.
        from pydantic import TypeAdapter

        key = TypeAdapter(Sha256).validate_python(request_key)
        path = self.directory / (key + ".json")
        try:
            if not path.exists():
                return None
            invocation = CodexInvocation.model_validate_json(path.read_bytes())
        except (OSError, ValueError) as error:
            raise ServiceError(
                "CODEX_TRACE_INVALID", "Invocation evidence cannot be read"
            ) from error
        if invocation.request_key != key:
            raise ServiceError(
                "CODEX_TRACE_INVALID", "Invocation evidence has a different identity"
            )
        return invocation

    def response(self, request_key: str) -> ProviderResponse | None:
        invocation = self.read(request_key)
        if invocation is None:
            return None
        if invocation.response is not None:
            return invocation.response
        return ProviderResponse(
            raw_json='{"transport":"codex-sdk","outcome":"unknown"}',
            output_text="",
            provider_request_id="codex-" + invocation.turn_id if invocation.turn_id else None,
            input_tokens=None,
            output_tokens=None,
            error_code="OUTCOME_UNKNOWN",
        )
