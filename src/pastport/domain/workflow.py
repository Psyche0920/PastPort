"""Workflow messages express intent and observations, never authentication proof."""

from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from pastport.domain.common import (
    ArtifactRef,
    Contract,
    EvidenceRequest,
    Identifier,
    NonNegative,
    Positive,
    Sha256,
    Text,
    ValidationIssue,
    Version,
)

NodeName = Literal[
    "register_project",
    "inventory_sources",
    "extract_candidates",
    "discover_story",
    "select_candidate",
    "research_evidence",
    "evidence_review",
    "draft_narrative",
    "narrative_review",
    "assemble_package",
    "validate_package",
    "publish_review",
    "publish_package",
]
RunStatus = Literal[
    "queued",
    "running",
    "waiting_review",
    "needs_changes",
    "needs_review",
    "budget_exhausted",
    "blocked",
    "failed",
    "cancelled",
    "no_feasible_story",
    "published",
]
ToolKind = Literal["lookup_local", "search_web", "read_source"]


class BudgetPolicy(Contract):
    max_model_requests: Positive
    max_input_tokens: Positive
    max_output_tokens: Positive
    max_search_requests: NonNegative
    max_fetch_requests: NonNegative
    max_active_seconds: Positive
    max_cost_microusd: Positive


class RemainingLimits(Contract):
    model_requests: NonNegative
    input_tokens: NonNegative
    output_tokens: NonNegative
    search_requests: NonNegative
    fetch_requests: NonNegative
    active_seconds: NonNegative
    cost_microusd: NonNegative


class WorkflowError(Contract):
    code: Identifier
    message: Text
    retryable: bool
    owner: Literal["evidence", "narrative", "assembly", "runtime", "workflow"]
    field_path: str


class WorkflowState(Contract):
    schema_version: Version
    project_id: Identifier
    run_id: Identifier
    graph_version: Identifier
    policy_ref: ArtifactRef
    revision: NonNegative
    node: NodeName
    status: RunStatus
    index_ref: ArtifactRef | None
    evidence_ref: ArtifactRef | None
    narrative_ref: ArtifactRef | None
    runtime_ref: ArtifactRef | None
    approved_route_ref: ArtifactRef | None
    selected_candidate_id: Identifier | None
    pending_review_id: Identifier | None
    pending_request_id: Identifier | None
    research_rounds_started: Annotated[int, Field(ge=0, le=2)]
    narrative_revisions_started: Annotated[int, Field(ge=0, le=2)]
    budget_id: Identifier
    usage_ledger_id: Identifier
    dirty_target_ids: tuple[Identifier, ...]
    last_error: WorkflowError | None

    @model_validator(mode="after")
    def local_references(self) -> Self:
        refs = (
            self.policy_ref,
            self.index_ref,
            self.evidence_ref,
            self.narrative_ref,
            self.runtime_ref,
            self.approved_route_ref,
        )
        if any(ref is not None and ref.project_id != self.project_id for ref in refs):
            raise ValueError("Cross-project workflow reference")
        if tuple(sorted(set(self.dirty_target_ids))) != self.dirty_target_ids:
            raise ValueError("Dirty IDs must be sorted and unique")
        return self


class ToolRequest(Contract):
    kind: ToolKind
    question_id: Identifier
    query: Text | None
    source_id: Identifier | None
    site_ids: tuple[Identifier, ...]
    limit: Annotated[int, Field(ge=1, le=5)]

    @model_validator(mode="after")
    def operation_arguments(self) -> Self:
        if self.kind == "read_source":
            if self.source_id is None or self.query is not None:
                raise ValueError("read_source requires a registered source ID and no query")
        elif self.query is None or self.source_id is not None:
            raise ValueError("Search requires a query and no source ID")
        return self


class SkillResult[T: Contract](Contract):
    request_id: Identifier
    skill: Literal["evidence-review", "narrative"]
    mode: Literal["index", "research", "review", "discover", "draft", "revise"]
    input_refs: tuple[ArtifactRef, ...]
    decision: Literal[
        "complete",
        "request_tool",
        "research_required",
        "changes_required",
        "review_required",
        "blocked",
        "no_feasible_story",
    ]
    reason_code: Identifier
    reason: Text
    payload: T | None
    issues: tuple[ValidationIssue, ...]
    changed_ids: tuple[Identifier, ...]
    evidence_requests: tuple[EvidenceRequest, ...]
    tool_request: ToolRequest | None

    @model_validator(mode="after")
    def control_payload(self) -> Self:
        modes = {
            "evidence-review": {"index", "research", "review"},
            "narrative": {"discover", "draft", "revise", "review"},
        }
        if self.mode not in modes[self.skill]:
            raise ValueError("Invalid Skill/mode combination")
        tool_allowed = self.skill == "evidence-review" and self.mode == "research"
        if self.decision == "request_tool":
            if not tool_allowed or self.tool_request is None:
                raise ValueError("Only evidence research may request one typed tool")
        elif self.tool_request is not None:
            raise ValueError("Unexpected tool request")
        if self.decision == "complete" and self.payload is None:
            raise ValueError("Complete requires a typed payload")
        if self.decision == "research_required" and not self.evidence_requests:
            raise ValueError("Research requires concrete evidence requests")
        if self.decision == "changes_required" and not self.changed_ids:
            raise ValueError("Changes require affected IDs")
        return self


class NodeResult(Contract):
    outcome: Literal["ok", "research_required", "changes_required", "blocked", "no_feasible_story"]
    output_refs: tuple[ArtifactRef, ...]
    issues: tuple[ValidationIssue, ...]
    next_action: NodeName | None


class ExecutionMetadata(Contract):
    project_id: Identifier
    run_id: Identifier
    operation_id: Identifier
    execution_key: Sha256
    input_refs: tuple[ArtifactRef, ...]
    policy_ref: ArtifactRef
    skill_ref: ArtifactRef | None
    model_config_ref: ArtifactRef | None
    budget_reservation_id: Identifier
    actor_id: Identifier
    deadline: AwareDatetime
    remaining_limits: RemainingLimits
    allowed_tools: tuple[ToolKind, ...]

    @field_validator("deadline")
    @classmethod
    def utc_deadline(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("Deadline must be UTC")
        return value

    @model_validator(mode="after")
    def local_inputs(self) -> Self:
        refs = (*self.input_refs, self.policy_ref, self.skill_ref, self.model_config_ref)
        if any(ref and ref.project_id != self.project_id for ref in refs):
            raise ValueError("Cross-project execution metadata")
        return self
