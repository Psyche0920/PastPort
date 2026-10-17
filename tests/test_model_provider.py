"""Provider wire behavior is tested through HTTPX without contacting a paid API."""

import asyncio
import json

import httpx
import pytest

from pastport.adapters.model_provider import OpenAIResponsesProvider
from pastport.application.execution_models import ProviderRequest
from pastport.application.model_gateway import strict_schema
from pastport.application.models import ServiceError
from pastport.domain.evidence import SourceManifestDraft


def request() -> ProviderRequest:
    return ProviderRequest(
        request_key="a" * 64,
        model="configured-snapshot",
        instructions="Return typed JSON.",
        input_text='{"documents":[]}',
        output_schema_json='{"type":"object","properties":{},"required":[],"additionalProperties":false}',
        maximum_output_tokens=1000,
    )


def response_body(**changes: object) -> dict[str, object]:
    result: dict[str, object] = dict(
        id="resp-1",
        model="configured-snapshot",
        status="completed",
        output=[dict(type="message", content=[dict(type="output_text", text='{"answer":"yes"}')])],
        usage=dict(input_tokens=12, output_tokens=8),
    )
    result.update(changes)
    return result


def test_provider_pins_endpoint_model_schema_and_storage_options() -> None:
    calls = []

    def handler(wire: httpx.Request) -> httpx.Response:
        calls.append(wire)
        assert str(wire.url) == "https://api.openai.com/v1/responses"
        body = json.loads(wire.content)
        assert body["store"] is False and body["stream"] is False and body["tools"] == []
        assert body["truncation"] == "disabled" and body["max_output_tokens"] == 1000
        assert body["text"]["format"]["type"] == "json_schema" and body["text"]["format"]["strict"]
        return httpx.Response(200, json=response_body(), headers={"x-request-id": "req-1"})

    provider = OpenAIResponsesProvider("unit-test-secret", transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.respond(request(), 1))
    assert len(calls) == 1 and result.input_tokens == 12 and result.output_tokens == 8
    assert result.output_text == '{"answer":"yes"}' and result.provider_request_id == "req-1"


@pytest.mark.parametrize(
    "status,code,known",
    [
        (401, "PROVIDER_AUTHENTICATION_FAILED", True),
        (403, "PROVIDER_FORBIDDEN", True),
        (404, "MODEL_UNAVAILABLE", True),
        (429, "PROVIDER_RATE_LIMITED", True),
        (500, "PROVIDER_OUTCOME_UNKNOWN", False),
        (302, "PROVIDER_OUTCOME_UNKNOWN", False),
    ],
)
def test_http_errors_are_specific_and_never_follow_redirects(
    status: int, code: str, known: bool
) -> None:
    calls = []

    def handler(wire: httpx.Request) -> httpx.Response:
        calls.append(wire)
        return httpx.Response(
            status,
            json={"error": "untrusted-provider-detail"},
            headers={"location": "https://unsafe.example"},
        )

    provider = OpenAIResponsesProvider("unit-test-secret", transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.respond(request(), 1))
    assert len(calls) == 1 and result.error_code == code and result.known_rejection is known
    assert result.input_tokens == (0 if known else None)


@pytest.mark.parametrize(
    "case,code",
    [
        ("model", "MODEL_CHANGED"),
        ("incomplete", "MODEL_INCOMPLETE"),
        ("refusal", "MODEL_REFUSED"),
        ("usage", None),
        ("json", "PROVIDER_RESPONSE_INVALID"),
    ],
)
def test_output_errors_preserve_usage_when_the_provider_reported_it(
    case: str, code: str | None
) -> None:
    body = response_body()
    if case == "model":
        body["model"] = "another-model"
    if case == "incomplete":
        body["status"] = "incomplete"
    if case == "refusal":
        body["output"] = [
            dict(type="message", content=[dict(type="refusal", refusal="Cannot comply")])
        ]
    if case == "usage":
        body["usage"] = None
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"invalid-json")
        if case == "json"
        else httpx.Response(200, json=body)
    )
    result = asyncio.run(
        OpenAIResponsesProvider("unit-test-secret", transport=transport).respond(request(), 1)
    )
    assert result.error_code == code
    assert result.input_tokens == (None if case in ("usage", "json") else 12)


def test_transport_timeout_is_unknown_and_does_not_retry() -> None:
    calls = []

    def handler(wire: httpx.Request) -> httpx.Response:
        calls.append(wire)
        raise httpx.ReadTimeout("Untrusted transport text", request=wire)

    with pytest.raises(ServiceError) as failure:
        asyncio.run(
            OpenAIResponsesProvider(
                "unit-test-secret", transport=httpx.MockTransport(handler)
            ).respond(request(), 1)
        )
    assert len(calls) == 1 and failure.value.code == "OUTCOME_UNKNOWN"
    assert "unit-test-secret" not in str(failure.value) and "Untrusted transport" not in str(
        failure.value
    )


def test_schema_normalization_keeps_real_title_and_default_property_names() -> None:
    schema = strict_schema(SourceManifestDraft.model_json_schema())
    assert isinstance(schema, dict)
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    source = definitions["Source"]
    assert isinstance(source, dict)
    properties = source["properties"]
    assert isinstance(properties, dict) and "title" in properties
    required = source["required"]
    assert isinstance(required, list) and "title" in required


def test_provider_response_has_a_byte_limit() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, content=b"x" * (1024 * 1024 + 1), headers={"x-request-id": "req-too-large"}
        )
    )
    result = asyncio.run(
        OpenAIResponsesProvider("unit-test-secret", transport=transport).respond(request(), 1)
    )
    assert result.error_code == "PROVIDER_RESPONSE_TOO_LARGE" and result.input_tokens is None
    assert result.provider_request_id == "req-too-large" and result.raw_json == ""
