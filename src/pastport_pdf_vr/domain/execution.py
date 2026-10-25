"""Bounded standalone subscription execution; no fabricated dollar accounting."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.models import DomainModel, ProjectId, ResourceId


class SubscriptionGrant(DomainModel):
    grant_ref: ResourceId
    project_id: ProjectId
    model_id: Annotated[str, Field(min_length=1, max_length=160)] = "gpt-6.1-sol"
    effort: Literal["low", "medium", "high"] = "medium"
    max_calls: Annotated[int, Field(ge=1, le=100)] = 8
    max_recorded_tokens: Annotated[int, Field(ge=1, le=10_000_000)] = 100_000
    timeout_seconds: Annotated[int, Field(ge=1, le=600)] = 120


class ExecutionInput(DomainModel):
    project_id: ProjectId
    grant_ref: ResourceId
    model_id: str
    kind: Literal["environment_generation"]
    prompt_version: str
    policy_version: str
    instructions: Annotated[str, Field(min_length=1, max_length=40_000)]
    payload_json: Annotated[str, Field(min_length=1, max_length=1_000_000)]
    output_schema_json: Annotated[str, Field(min_length=1, max_length=200_000)]
    transport_policy: Literal["codex-subscription-v1"] = "codex-subscription-v1"
    image_paths: tuple[str, ...] = ()
    image_hashes: tuple[str, ...] = ()


class ExecutionOutput(DomainModel):
    payload_json: str
    receipt_ref: ResourceId
    thread_ref: str
    turn_ref: str
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    total_tokens: Annotated[int, Field(ge=0)]
    auth_mode: Literal["chatgpt"] = "chatgpt"
    billing_basis: Literal["subscription_allowance"] = "subscription_allowance"


class SDKReadiness(DomainModel):
    authenticated: bool
    auth_mode: str
    requested_model: str
    model_available: bool
    image_input_supported: bool


class ModelExecutionError(RuntimeError):
    """Execution failed without implicit retry, fallback or inferred billing."""


class ExecutionDenied(ModelExecutionError):
    """A grant, authentication, capability or quota prevents dispatch."""


class ExecutionRecoveryRequired(ModelExecutionError):
    """A prior dispatch has uncertain effects; an operator must reconcile it."""
