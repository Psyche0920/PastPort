"""Pinned execution configuration and durable receipts, independent of provider SDKs."""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self, runtime_checkable

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

STORY_CODEX_MODEL = "gpt-6.1-sol"

BoundedText = Annotated[str, Field(max_length=1024 * 1024)]


class ModelPolicy(Contract):
    role: Literal["research", "story"]
    provider: Literal["fake", "openai", "codex"]
    model: Text
    price_version: Identifier
    input_microusd_per_million: NonNegative
    output_microusd_per_million: NonNegative
    maximum_input_tokens: Positive = 32768
    maximum_output_tokens: Positive = 4096
    references: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def codex_story_scope(self) -> Self:
        if self.provider == "codex" and (
            self.role != "story"
            or self.model != STORY_CODEX_MODEL
            or self.input_microusd_per_million != 0
            or self.output_microusd_per_million != 0
        ):
            raise ValueError("Codex story generation permits only Sol 6.1 High")
        return self

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        return (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
            + 999999
        ) // 1000000


class ExecutionSettings(Contract):
    models: tuple[ModelPolicy, ...] = ()
    allowed_tools: tuple[ToolKind, ...] = ()
    timeout_seconds: Annotated[int, Field(ge=1, le=300)] = 120
    maximum_source_bytes: Annotated[int, Field(ge=1, le=64 * 1024 * 1024)] = 262144

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


@runtime_checkable
class RecordedModelProvider(Protocol):
    def recorded_response(self, request_key: str) -> ProviderResponse | None: ...


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    name: Literal["fake", "openai", "codex"]
    provider: ModelProvider


class ExecutionSummary(Contract):
    operation_id: Identifier
    receipt_hash: Sha256
    artifact_ref: "ArtifactRef | None"
    settlement: UsageSettlement | None
    error_code: Identifier | None
