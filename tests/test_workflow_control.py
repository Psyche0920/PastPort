"""Skill control translation preserves the frozen module vocabulary and human authority."""

from typing import Literal

import pytest
from test_service import FIXTURES

from pastport.application.workflow_control import SkillResultMapper
from pastport.domain.modules import CandidateSetDraft, ModuleResult
from pastport.domain.workflow import SkillResult


@pytest.mark.parametrize("ready", [True, False])
def test_review_required_routes_only_valid_handoff_payloads(ready: bool) -> None:
    comparison = (
        ModuleResult[CandidateSetDraft]
        .model_validate_json((FIXTURES / "discover-result.json").read_bytes())
        .payload
    )
    assert comparison is not None
    result = SkillResult[CandidateSetDraft](
        request_id="professional-review",
        skill="narrative",
        mode="discover",
        input_refs=(),
        decision="review_required",
        reason_code="HUMAN_DECISION",
        reason="Human must decide",
        payload=comparison if ready else None,
        issues=(),
        changed_ids=(),
        evidence_requests=(),
        tool_request=None,
    )
    mapped = SkillResultMapper.to_module_result(result, ModuleResult[CandidateSetDraft])
    assert mapped.outcome == ("completed" if ready else "blocked")
    assert mapped.payload == (comparison if ready else None)
    assert any(i.code == "REVIEW_REQUIRED" for i in mapped.issues) is (not ready)


@pytest.mark.parametrize("decision", ["complete", "blocked", "no_feasible_story"])
def test_other_skill_decisions_keep_their_declared_control_meaning(
    decision: Literal["complete", "blocked", "no_feasible_story"],
) -> None:
    comparison = (
        ModuleResult[CandidateSetDraft]
        .model_validate_json((FIXTURES / "discover-result.json").read_bytes())
        .payload
    )
    assert comparison is not None
    result = SkillResult[CandidateSetDraft](
        request_id="control",
        skill="narrative",
        mode="discover",
        input_refs=(),
        decision=decision,
        reason_code="DECISION",
        reason="Documented decision",
        payload=comparison if decision == "complete" else None,
        issues=(),
        changed_ids=(),
        evidence_requests=(),
        tool_request=None,
    )
    mapped = SkillResultMapper.to_module_result(result, ModuleResult[CandidateSetDraft])
    assert mapped.outcome == ("completed" if decision == "complete" else decision)


def test_tool_requests_remain_blocked_until_shared_execution_is_available() -> None:
    from pastport.domain.modules import EvidenceFindings
    from pastport.domain.workflow import ToolRequest

    result = SkillResult[EvidenceFindings](
        request_id="research-tool",
        skill="evidence-review",
        mode="research",
        input_refs=(),
        decision="request_tool",
        reason_code="SOURCE_NEEDED",
        reason="Read the registered source",
        payload=None,
        issues=(),
        changed_ids=(),
        evidence_requests=(),
        tool_request=ToolRequest(
            kind="read_source",
            question_id="question-1",
            query=None,
            source_id="source-1",
            site_ids=("site-1",),
            limit=1,
        ),
    )
    mapped = SkillResultMapper.to_module_result(result, ModuleResult[EvidenceFindings])
    assert mapped.outcome == "blocked"
    assert any(i.code == "TOOL_EXECUTION_UNAVAILABLE" for i in mapped.issues)
