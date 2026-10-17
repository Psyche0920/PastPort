"""Pinned execution configuration and durable receipts, independent of provider SDKs."""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from pastport.application.models import StoredArtifact
from pastport.application.reliability import UsageSettlement
from pastport.domain.common import (
    ArtifactRef,
    Contract,
    Identifier,
    NonNegative,
    Positive,
    Sha256,
    Text,
)
from pastport.domain.workflow import ExecutionMetadata, ToolKind

BoundedText = Annotated[str, Field(max_length=1024 * 1024)]


class ModelPolicy(Contract):
    role: Literal["research", "story"]
    provider: Literal["fake", "openai"]
    model: Text
    price_version: Identifier
    input_microusd_per_million: NonNegative
    output_microusd_per_million: NonNegative
    maximum_input_tokens: Positive = 32768
    maximum_output_tokens: Positive = 4096
    references: tuple[Text, ...] = ()

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        return (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
            + 999999
        ) // 1000000


class ExecutionSettings(Contract):
    models: tuple[ModelPolicy, ...] = ()
    allowed_tools: tuple[ToolKind, ...] = ()
    timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 120
    maximum_source_bytes: Annotated[int, Field(ge=1, le=262144)] = 262144

    @model_validator(mode="after")
    def unique_roles(self) -> Self:
        if len({m.role for m in self.models}) != len(self.models):
            raise ValueError("Configure one pinned model per role")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("Tools must be unique")
        return self


class SkillFile(Contract):
    path: Text
    sha256: Sha256
    text: BoundedText


class SkillBundle(Contract):
    name: Literal["evidence-review", "narrative"]
    version: Identifier
    files: tuple[SkillFile, ...] = Field(min_length=1)


class ExecutionBinding(Contract):
    settings: ExecutionSettings
    skills: tuple[SkillBundle, ...]


class ProviderRequest(Contract):
    request_key: Sha256
    model: Text
    instructions: BoundedText
    input_text: BoundedText
    output_schema_json: BoundedText
    maximum_output_tokens: Positive


class ProviderResponse(Contract):
    raw_json: BoundedText
    output_text: BoundedText
    provider_request_id: Text | None
    input_tokens: NonNegative | None
    output_tokens: NonNegative | None
    error_code: Identifier | None = None
    known_rejection: bool = False


class ExecutionGrant(Contract):
    metadata: ExecutionMetadata
    request_json: BoundedText


class ExecutionReceipt(Contract):
    response: ProviderResponse | None = None
    artifact: StoredArtifact | None = None
    settlement: UsageSettlement | None = None
    error_code: Identifier | None = None


class ModelProvider(Protocol):
    async def respond(
        self, request: ProviderRequest, timeout_seconds: float
    ) -> ProviderResponse: ...


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    name: Literal["fake", "openai"]
    provider: ModelProvider


class ExecutionSummary(Contract):
    operation_id: Identifier
    receipt_hash: Sha256
    artifact_ref: "ArtifactRef | None"
    settlement: UsageSettlement | None
    error_code: Identifier | None
