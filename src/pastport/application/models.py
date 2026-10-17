"""Application records use clear names and reuse the frozen shared contracts."""

from typing import Literal

from pydantic import Field

from pastport.application.workflow_control import WorkflowControl
from pastport.domain.common import (
    ArtifactRef,
    Contract,
    Identifier,
    ProjectRequirements,
    ReviewDecision,
    Sha256,
    Text,
)
from pastport.domain.modules import LockedField, NarrativeDraft, SelectedCandidate
from pastport.domain.packages import ReviewTarget
from pastport.domain.workflow import BudgetPolicy, NodeName, WorkflowState


class ServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class Actor(Contract):
    actor_id: Identifier
    roles: tuple[Literal["editor", "evidence", "narrative", "publisher", "operator"], ...]
    project_ids: tuple[Identifier, ...] | None


class ProjectRecord(Contract):
    project_id: Identifier
    name: Text
    provider: Literal["local_manifest", "google_drive"]
    folder_id: Identifier
    requirements: ProjectRequirements
    created_by: Identifier


class CreateProject(Contract):
    name: Text
    provider: Literal["local_manifest", "google_drive"]
    folder_id: Identifier
    requirements: ProjectRequirements


class CreateRun(Contract):
    budget_policy: BudgetPolicy
    policy_ref: ArtifactRef


class StoredArtifact(Contract):
    reference: ArtifactRef
    payload_json: str


class ReviewRequest(Contract):
    request_id: Identifier
    gate: Literal["evidence", "narrative", "publication"]
    targets: tuple[ReviewTarget, ...] = Field(min_length=1)


class ReviewChoice(Contract):
    target_id: Identifier
    target_version: Identifier
    target_hash: Sha256
    decision: Literal["approved", "changes_requested", "rejected"]
    reason: Text


class SubmitReview(Contract):
    rework_owner: Literal["evidence", "narrative", "assembly"] | None = None
    expected_revision: int = Field(ge=0)
    request_id: Identifier
    decisions: tuple[ReviewChoice, ...] = Field(min_length=1)


class SelectCandidate(Contract):
    expected_revision: int = Field(ge=0)
    candidate_set_hash: Sha256
    candidate_id: Identifier
    reason: Text


class RunCommand(Contract):
    expected_revision: int = Field(ge=0)
    reason: Text


class RunRecord(Contract):
    state: WorkflowState
    budget_policy: BudgetPolicy
    artifacts: tuple[StoredArtifact, ...]
    review_requests: tuple[ReviewRequest, ...]
    review_decisions: tuple[ReviewDecision, ...]
    selected_candidate: SelectedCandidate | None
    environment: Literal["test", "production"]
    created_by: Identifier
    current_release_id: Identifier | None
    locked_fields: tuple[LockedField, ...] = ()
    expected_old_release: Identifier | None = None
    control: WorkflowControl = Field(default_factory=WorkflowControl)


class RunEvent(Contract):
    event_id: int
    run_id: Identifier
    revision: int
    node: NodeName
    status: str
    message: str


class StoredCommand(Contract):
    command_id: Identifier
    run_id: Identifier


class RequestReceipt(Contract):
    scope: str
    request_key: str
    payload_hash: Sha256
    response_json: str
    status_code: int


class SubmitRevision(Contract):
    expected_revision: int = Field(ge=0)
    reason: Text
    replacement_story: NarrativeDraft
    facts_changed: bool


class SetLocks(Contract):
    expected_revision: int = Field(ge=0)
    json_pointers: tuple[Text, ...]
    reason: Text


class LocalExecutionPolicy(Contract):
    version: str = "local-4"
    environment: Literal["test", "production"]
    graph_version: str = "editorial-4"
    external_model_calls: bool = False
    external_tools: tuple[Literal["lookup_local", "read_source", "search_web"], ...] = ()
    execution_config_hash: Sha256 | None = None
    maximum_research_rounds: Literal[2] = 2
