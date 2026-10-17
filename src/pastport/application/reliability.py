"""Typed authority, accounting and release records shared by local service boundaries."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from pastport.application.models import Actor, ServiceError
from pastport.domain.common import (
    ArtifactRef,
    Contract,
    Environment,
    Identifier,
    NonNegative,
    Positive,
    ReviewDecision,
    Sha256,
    Text,
)
from pastport.domain.workflow import BudgetPolicy, NodeName


class ReviewAuthority:
    """Revalidate stored approvals against the currently configured server accounts."""

    def __init__(self, actors: tuple[Actor, ...], environment: Environment) -> None:
        if len({actor.actor_id for actor in actors}) != len(actors):
            raise ValueError("Configured actor identities must be unique")
        self.actors = {actor.actor_id: actor for actor in actors}
        self.environment = environment

    def actor(self, actor_id: str, project_id: str, role: str) -> Actor:
        actor = self.actors.get(actor_id)
        if (
            actor is None
            or role not in actor.roles
            or (actor.project_ids is not None and project_id not in actor.project_ids)
        ):
            raise ServiceError(
                "APPROVAL_AUTHORITY_LOST", "Reviewer no longer has project and gate authority", 403
            )
        return actor

    def decision(self, decision: ReviewDecision, project_id: str) -> None:
        if decision.environment != self.environment:
            raise ServiceError(
                "REVIEW_ENVIRONMENT_MISMATCH", "Review belongs to another environment"
            )
        self.actor(
            decision.actor_id,
            project_id,
            "publisher" if decision.gate == "publication" else decision.gate,
        )


class Usage(Contract):
    model_requests: NonNegative = 0
    input_tokens: NonNegative = 0
    output_tokens: NonNegative = 0
    search_requests: NonNegative = 0
    fetch_requests: NonNegative = 0
    active_milliseconds: NonNegative = 0
    cost_microusd: NonNegative = 0

    def plus(self, other: "Usage") -> "Usage":
        return Usage.model_validate(
            {name: getattr(self, name) + getattr(other, name) for name in type(self).model_fields}
        )

    def fits(self, maximum: "Usage") -> bool:
        return all(
            getattr(self, name) <= getattr(maximum, name) for name in type(self).model_fields
        )

    @classmethod
    def limits(cls, policy: BudgetPolicy) -> "Usage":
        return cls(
            model_requests=policy.max_model_requests,
            input_tokens=policy.max_input_tokens,
            output_tokens=policy.max_output_tokens,
            search_requests=policy.max_search_requests,
            fetch_requests=policy.max_fetch_requests,
            active_milliseconds=policy.max_active_seconds * 1000,
            cost_microusd=policy.max_cost_microusd,
        )


class OperationReservation(Contract):
    operation_id: Identifier
    run_id: Identifier
    input_hash: Sha256
    reserved: Usage
    price_reference: Text | None = None
    group_key: Identifier | None = None
    maximum_group_operations: Positive | None = None


class UsageSettlement(Contract):
    actual: Usage
    provider_request_id: Text | None = None
    source: Literal["local", "provider", "operator"] = "local"


class LedgerEntry(Contract):
    reservation_id: Identifier
    operation_id: Identifier
    run_id: Identifier
    state: Literal["reserved", "settled", "unknown"]
    reserved: Usage
    settlement: UsageSettlement | None
    price_reference: Text | None


class BudgetSnapshot(Contract):
    run_id: Identifier
    limit: Usage
    used: Usage
    held: Usage
    entries: tuple[LedgerEntry, ...]
    over_limit: bool


class ExecutionIdentity(Contract):
    project_id: Identifier
    run_id: Identifier
    node: NodeName
    graph_version: Identifier
    policy_ref: ArtifactRef
    input_refs: tuple[ArtifactRef, ...]
    budget_policy: BudgetPolicy
    selection_hash: Sha256 | None


class RevokeReview(Contract):
    expected_revision: NonNegative
    decision_id: Identifier
    reason: Text


class ReviewRevocation(Contract):
    kind: Literal["human", "dependency"] = "human"
    decision_id: Identifier
    run_id: Identifier
    actor_id: Identifier
    reason: Text
    created_at: datetime


class ReleaseFile(Contract):
    relative_path: Text
    sha256: Sha256


class ReleaseManifest(Contract):
    project_id: Identifier
    run_id: Identifier
    release_id: Identifier
    environment: Environment
    runtime_ref: ArtifactRef
    files: tuple[ReleaseFile, ...] = Field(min_length=1)
    review_decision_ids: tuple[Identifier, ...] = Field(min_length=1)


class ReleaseRecord(Contract):
    manifest: ReleaseManifest
    manifest_sha256: Sha256
    expected_old_release: Identifier | None
    status: Literal["staged", "published", "retired"] = "staged"
