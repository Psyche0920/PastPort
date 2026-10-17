"""Bounded Responses HTTP adapter and explicit deterministic test provider."""

import json
from collections.abc import Callable
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pastport.application.execution_models import ProviderRequest, ProviderResponse
from pastport.application.models import ServiceError


class WireUsage(BaseModel):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    model_config = ConfigDict(strict=True, extra="ignore")


class WireContent(BaseModel):
    type: str
    text: str = ""
    model_config = ConfigDict(strict=True, extra="ignore")


class WireOutput(BaseModel):
    type: str
    content: list[WireContent] = Field(default_factory=list)
    model_config = ConfigDict(strict=True, extra="ignore")


class WireResponse(BaseModel):
    id: str
    model: str
    status: str
    output: list[WireOutput]
    usage: WireUsage | None = None
    model_config = ConfigDict(strict=True, extra="ignore")


class OpenAIResponsesProvider:
    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not api_key or any(c in api_key for c in "\r\n"):
            raise ValueError("A server-owned API key is required")
        self._api_key = api_key
        self.transport = transport

    async def respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        try:
            return await self._respond(request, timeout_seconds)
        except httpx.TransportError as error:
            raise ServiceError(
                "OUTCOME_UNKNOWN",
                "Provider transport failed after dispatch; reconcile before retry",
            ) from error

    async def _respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        body = dict(
            model=request.model,
            instructions=request.instructions,
            input=request.input_text,
            max_output_tokens=request.maximum_output_tokens,
            store=False,
            stream=False,
            tools=[],
            truncation="disabled",
            text=dict(
                format=dict(
                    type="json_schema",
                    name="pastport_output",
                    schema=json.loads(request.output_schema_json),
                    strict=True,
                )
            ),
        )
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        ) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/responses",
                json=body,
                headers={
                    "Authorization": "Bearer " + self._api_key,
                    "X-Client-Request-Id": request.request_key,
                },
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        return ProviderResponse(
                            raw_json="",
                            output_text="",
                            provider_request_id=response.headers.get("x-request-id"),
                            input_tokens=None,
                            output_tokens=None,
                            error_code="PROVIDER_RESPONSE_TOO_LARGE",
                        )
                raw = bytes(data).decode("utf-8", errors="replace")
                request_id = response.headers.get("x-request-id")
                if response.status_code != 200:
                    known = response.status_code in (400, 401, 403, 404, 422, 429)
                    code = {
                        401: "PROVIDER_AUTHENTICATION_FAILED",
                        403: "PROVIDER_FORBIDDEN",
                        404: "MODEL_UNAVAILABLE",
                        429: "PROVIDER_RATE_LIMITED",
                    }.get(
                        response.status_code,
                        "PROVIDER_REQUEST_REJECTED" if known else "PROVIDER_OUTCOME_UNKNOWN",
                    )
                    return ProviderResponse(
                        raw_json=raw,
                        output_text="",
                        provider_request_id=request_id,
                        input_tokens=0 if known else None,
                        output_tokens=0 if known else None,
                        error_code=code,
                        known_rejection=known,
                    )
        try:
            result = WireResponse.model_validate_json(raw)
        except ValidationError:
            return ProviderResponse(
                raw_json=raw,
                output_text="",
                provider_request_id=request_id,
                input_tokens=None,
                output_tokens=None,
                error_code="PROVIDER_RESPONSE_INVALID",
            )
        content = [
            part for item in result.output if item.type == "message" for part in item.content
        ]
        refused = any(part.type == "refusal" for part in content)
        text = "".join(part.text for part in content if part.type == "output_text")
        error = (
            "MODEL_CHANGED"
            if result.model != request.model
            else "MODEL_REFUSED"
            if refused
            else "MODEL_INCOMPLETE"
            if result.status != "completed"
            else None
        )
        return ProviderResponse(
            raw_json=raw,
            output_text=text,
            provider_request_id=request_id or result.id,
            input_tokens=result.usage.input_tokens if result.usage else None,
            output_tokens=result.usage.output_tokens if result.usage else None,
            error_code=error,
        )


class FakeModelProvider:
    def __init__(self, response: Callable[[ProviderRequest], ProviderResponse]) -> None:
        self.response = response

    async def respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        return self.response(request)
