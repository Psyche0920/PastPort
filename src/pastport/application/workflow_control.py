"""Durable control manifests; module suggestions cannot grant approval or reset limits."""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from pastport.domain.common import Contract, EvidenceRequest, Identifier, Text
from pastport.domain.evidence import SourceIndexDraft
from pastport.domain.modules import EvidenceFindings, RevisionRequest

if TYPE_CHECKING:
    from pastport.domain.modules import ModuleResult
    from pastport.domain.workflow import SkillResult


class ResearchRound(Contract):
    round_id: Identifier
    requests: tuple[EvidenceRequest, ...] = Field(min_length=1, max_length=8)
    index: SourceIndexDraft
    findings: tuple[EvidenceFindings, ...] = ()
    completed: bool = False


class RevisionRound(Contract):
    round_id: Identifier
    request: RevisionRequest
    completed: bool = False


class WorkflowControl(Contract):
    release_generation: int = Field(default=0, ge=0)
    retry_generation: int = Field(default=0, ge=0)
    action: Literal["draft", "revise", "review"] = "draft"
    pending_research: tuple[EvidenceRequest, ...] = ()
    research_return_action: Literal["discover", "draft", "revise"] = "draft"
    research_rounds: tuple[ResearchRound, ...] = ()
    revision_request: RevisionRequest | None = None
    revision_rounds: tuple[RevisionRound, ...] = ()
    professional_review: bool = False
    review_request_id: Identifier | None = None


class RequestNarrativeAction(Contract):
    expected_revision: int = Field(ge=0)
    action: Literal["revise", "review"]
    feedback: Text
    target_ids: tuple[Identifier, ...] = Field(min_length=1)


class SkillResultMapper:
    """Translate professional Skill decisions into the frozen module outcome vocabulary."""

    @staticmethod
    def to_module_result[Payload: Contract](
        result: "SkillResult[Payload]",
        result_type: type["ModuleResult[Payload]"],
    ) -> "ModuleResult[Payload]":
        from pastport.domain.common import ValidationIssue

        outcome: Literal[
            "completed", "research_required", "changes_required", "blocked", "no_feasible_story"
        ]
        issues = result.issues
        if result.decision == "review_required":
            ready = result.payload is not None and not any(i.severity == "blocking" for i in issues)
            outcome = "completed" if ready else "blocked"
            if not ready:
                issues = (
                    *issues,
                    ValidationIssue(
                        code="REVIEW_REQUIRED",
                        severity="blocking",
                        owner="evidence" if result.skill == "evidence-review" else "narrative",
                        artifact_id=None,
                        json_pointer="",
                        message=result.reason,
                        remediation="Resolve handoff gaps with an authenticated reviewer",
                    ),
                )
        elif result.decision == "request_tool":
            outcome = "blocked"
            issues = (
                *issues,
                ValidationIssue(
                    code="TOOL_EXECUTION_UNAVAILABLE",
                    severity="blocking",
                    owner="workflow",
                    artifact_id=None,
                    json_pointer="",
                    message="Shared tool execution is not configured",
                    remediation="Complete F5 and configure the shared executor before tool use",
                ),
            )
        else:
            outcome = "completed" if result.decision == "complete" else result.decision
        return result_type(
            outcome=outcome,
            payload=result.payload,
            issues=issues,
            evidence_requests=result.evidence_requests,
            changed_ids=result.changed_ids,
            reason=result.reason,
        )
