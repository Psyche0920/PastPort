"""Codex lifecycle tests use a local SDK counterpart and make no model calls."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pastport.adapters.codex_provider import CodexStoryProvider
from pastport.adapters.codex_traces import CodexTraceStore
from pastport.application.execution_models import ProviderRequest
from pastport.application.models import ServiceError


def request() -> ProviderRequest:
    return ProviderRequest(
        request_key="a" * 64,
        model="gpt-6.1-sol",
        instructions="private instructions",
        input_text="private PDF content",
        output_schema_json='{"type":"object"}',
        maximum_output_tokens=100,
    )


@pytest.mark.parametrize("phase", ["running", "complete", "cleanup"])
def test_trace_is_saved_before_waiting_and_known_usage_survives_cleanup_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    sdk = pytest.importorskip("openai_codex")
    from openai_codex.generated.v2_all import TurnStatus, TokenUsageBreakdown

    store = CodexTraceStore(tmp_path)
    calls = []

    class Handle:
        id = "turn-1"

        async def run(self) -> SimpleNamespace:
            saved = store.read(request().request_key)
            assert saved is not None and saved.turn_id == self.id and saved.state == "turn_started"
            if phase == "running":
                await asyncio.sleep(10)
            return SimpleNamespace(
                id=self.id,
                status=TurnStatus.completed,
                final_response='{"story":"candidate"}',
                usage=SimpleNamespace(total=TokenUsageBreakdown(
                    input_tokens=12, output_tokens=8, total_tokens=20,
                    cached_input_tokens=4, reasoning_output_tokens=3,
                )),
            )

    class Thread:
        id = "thread-1"

        async def turn(self, *args: object, **kwargs: object) -> Handle:
            calls.append(1)
            return Handle()

    class Client:
        def __init__(self, config: object) -> None:
            pass

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            if phase == "cleanup":
                await asyncio.sleep(10)

        async def account(self) -> SimpleNamespace:
            return SimpleNamespace(account=SimpleNamespace(root=SimpleNamespace(type="chatgpt")))

        async def thread_start(self, **kwargs: object) -> Thread:
            assert kwargs["ephemeral"] is True
            return Thread()

    monkeypatch.setattr(sdk, "AsyncCodex", Client)
    provider = CodexStoryProvider(trace_directory=tmp_path)
    if phase == "running":
        with pytest.raises(ServiceError, match="timed out"):
            asyncio.run(provider.respond(request(), 0.05))
        recovered = provider.recorded_response(request().request_key)
        assert recovered is not None and recovered.provider_request_id == "codex-turn-1"
        assert recovered.input_tokens is None and recovered.output_tokens is None
        assert recovered.error_code == "OUTCOME_UNKNOWN"
        with pytest.raises(ServiceError, match="refusing redispatch"):
            asyncio.run(provider.respond(request(), 0.05))
    else:
        result = asyncio.run(provider.respond(request(), 0.05))
        assert result.input_tokens == 12 and result.output_tokens == 8
        assert json.loads(result.raw_json)["usage"]["reasoning_output_tokens"] == 3
        assert result.output_text == '{"story":"candidate"}'
        assert provider.recorded_response(request().request_key) == result
        assert asyncio.run(provider.respond(request(), 0.05)) == result
    assert len(calls) == 1
    raw = (tmp_path / (request().request_key + ".json")).read_text()
    assert "private PDF content" not in raw and "private instructions" not in raw
    assert (tmp_path / (request().request_key + ".json")).stat().st_mode & 0o077 == 0
    assert json.loads(raw)["thread_id"] == "thread-1"
