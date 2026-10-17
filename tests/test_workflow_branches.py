"""Real HTTP/SQLite/graph branch tests with fixed, explicitly synthetic counterpart modules."""

import json
import time
from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from test_service import (
    FIXTURES,
    approve_gate,
    confirm_direction,
    create_run,
    headers,
    settings,
    wait_for,
)

from pastport.adapters.content import LocalContentFiles, LocalEvidenceAdapter, LocalNarrativeAdapter
from pastport.api.app import create_app
from pastport.application.models import RunRecord
from pastport.application.updates import updated
from pastport.domain.common import CanonicalSerializer, EvidenceRequest
from pastport.domain.evidence import SourceIndexDraft
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    EvidenceFindings,
    IndexRequest,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ResearchRequest,
    ReviseRequest,
)
from pastport.ports.modules import ExecutionContext


def gap(
    context: ExecutionContext, site_id: str, candidate_id: str | None = None
) -> EvidenceRequest:
    return EvidenceRequest(
        request_id="gap-" + context.metadata.execution_key[:12],
        project_id=context.metadata.project_id,
        purpose="direction" if candidate_id else "scope_gap",
        candidate_id=candidate_id,
        question="Verify the registered building function",
        reason="The premise needs a located source",
        affected_ids=(site_id,),
        existing_source_ids=(),
        required_evidence=("Located building-function evidence",),
    )


class BranchEvidence(LocalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__(LocalContentFiles(FIXTURES, allow_synthetic=True))
        self.requests: list[ResearchRequest] = []
        self.block_once = False
        self.index_gap = False

    async def index(
        self, request: IndexRequest, context: ExecutionContext
    ) -> ModuleResult[SourceIndexDraft]:
        result = await super().index(request, context)
        assert result.payload is not None
        if self.index_gap:
            return updated(
                result,
                outcome="research_required",
                evidence_requests=(gap(context, result.payload.sites[0].site_id),),
            )
        return result

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        self.requests.append(request)
        if self.block_once and len(self.requests) == 1:
            return ModuleResult[EvidenceFindings](
                outcome="blocked",
                payload=None,
                issues=(),
                evidence_requests=(),
                changed_ids=(),
                reason="A registered source is temporarily unavailable",
            )
        result = await super().research(request, context)
        assert result.payload is not None
        # A scope round updates the index without creating or approving a story direction.
        index = updated(result.payload.index, content_version="index-" + str(len(self.requests)))
        return updated(result, payload=updated(result.payload, index=index))


class BranchNarrative(LocalNarrativeAdapter):
    def __init__(
        self,
        mode: Literal[
            "normal", "scope", "scope_limit", "draft_gap", "change", "blocked", "no_feasible"
        ] = "normal",
    ) -> None:
        super().__init__(LocalContentFiles(FIXTURES, allow_synthetic=True))
        self.mode = mode
        self.discoveries = 0
        self.drafts = 0
        self.revisions: list[ReviseRequest] = []
        self.reviews = 0
        self.keep_changing = False
        self.break_lock = False
        self.stale_review = False
        self.review_changes_once = False
        self.revision_gap_once = False

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        self.discoveries += 1
        result = await super().discover(request, context)
        if self.mode in ("scope", "scope_limit") and (
            self.discoveries == 1 or self.mode == "scope_limit"
        ):
            return updated(
                result,
                outcome="research_required",
                payload=None,
                evidence_requests=(gap(context, request.index.sites[0].site_id),),
            )
        if self.mode == "no_feasible":
            return updated(
                result,
                outcome="no_feasible_story",
                payload=None,
                reason="A model proposes stopping",
            )
        return result

    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        self.drafts += 1
        result = await super().draft(request, context)
        if self.mode == "draft_gap" and self.drafts == 1:
            return updated(
                result,
                outcome="research_required",
                payload=None,
                evidence_requests=(
                    gap(
                        context,
                        request.evidence.evidence.sites[0].site_id,
                        request.selected_candidate.candidate_id,
                    ),
                ),
            )
        if self.mode == "blocked" and self.drafts == 1:
            return updated(
                result, outcome="blocked", payload=None, reason="Narrative configuration is missing"
            )
        if self.mode == "change":
            assert result.payload is not None
            return updated(
                result,
                outcome="changes_required",
                changed_ids=(result.payload.package.game.chapter_id,),
                reason="Make the consequence visible",
            )
        return result

    async def revise(
        self, request: ReviseRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        self.revisions.append(request)
        context.cancellation.raise_if_cancelled()
        result = await super().draft(request.draft_request, context)
        assert result.payload is not None
        if self.revision_gap_once and len(self.revisions) == 1:
            return updated(
                result,
                outcome="research_required",
                payload=None,
                evidence_requests=(
                    gap(
                        context,
                        request.draft_request.evidence.evidence.sites[0].site_id,
                        request.draft_request.selected_candidate.candidate_id,
                    ),
                ),
            )
        raw = json.loads(result.payload.model_dump_json())
        if self.break_lock:
            raw["package"]["game"]["locales"][0]["entries"][0]["text"] = (
                "Incorrectly changed protected text"
            )
        else:
            raw["package"]["game"]["locales"][0]["entries"][1]["text"] = (
                "A revised visible consequence"
            )
        return updated(
            result,
            payload=NarrativeDraft.model_validate_json(json.dumps(raw)),
            outcome="changes_required" if self.keep_changing else "completed",
            changed_ids=(result.payload.package.game.chapter_id,) if self.keep_changing else (),
            reason="Revise the consequence again"
            if self.keep_changing
            else "Revision ready for human review",
        )

    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]:
        self.reviews += 1
        result = await super().review(request, context)
        assert result.payload is not None
        if self.stale_review:
            return updated(
                result,
                payload=updated(
                    result.payload,
                    narrative_ref=updated(result.payload.narrative_ref, sha256="0" * 64),
                ),
            )
        if self.review_changes_once and self.reviews == 1:
            return updated(
                result,
                outcome="changes_required",
                changed_ids=(request.narrative.package.game.chapter_id,),
                reason="Professional counterexample requires a revision",
            )
        return result


def record(client: TestClient, run_id: str) -> RunRecord:
    return RunRecord.model_validate_json(
        client.get("/api/v1/runs/" + run_id, headers=headers()).content
    )


def stopped(client: TestClient, run_id: str, status: str) -> RunRecord:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = record(client, run_id)
        if result.state.status == status:
            return result
        if (
            result.state.status in ("failed", "blocked", "needs_review")
            and result.state.node != "select_candidate"
        ):
            pytest.fail(str(result.state))
        time.sleep(0.02)
    pytest.fail("Run did not stop at " + status)


def reject_gate(client: TestClient, run_id: str, *, reject: bool = False) -> RunRecord:
    run = wait_for(client, run_id, "waiting_review")
    pending = next(r for r in run.review_requests if r.request_id == run.state.pending_review_id)
    response = client.post(
        "/api/v1/runs/" + run_id + "/review-decisions",
        headers=headers(),
        json=dict(
            expected_revision=run.state.revision,
            request_id=pending.request_id,
            decisions=[
                dict(
                    target_id=t.target_id,
                    target_version=t.version,
                    target_hash=t.sha256,
                    decision="rejected" if reject else "changes_requested",
                    reason="Correct these premises or consequences",
                )
                for t in pending.targets
            ],
        ),
    )
    assert response.status_code == 202, response.text
    return run


def action(client: TestClient, run_id: str, kind: str) -> RunRecord:
    run = wait_for(client, run_id, "waiting_review")
    response = client.post(
        "/api/v1/runs/" + run_id + "/narrative-requests",
        headers=headers(),
        json=dict(
            expected_revision=run.state.revision,
            action=kind,
            feedback="Check the consequence",
            target_ids=[run_id + ":narrative"],
        ),
    )
    assert response.status_code == 202, response.text
    return run


def test_scope_research_returns_to_discovery_then_keeps_shared_round_limit(tmp_path: Path) -> None:
    evidence, narrative = BranchEvidence(), BranchNarrative("scope")
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=narrative)
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        ready = wait_for(client, run_id, "waiting_review")
        assert ready.state.research_rounds_started == 2
        assert [r.evidence_request.purpose for r in evidence.requests] == ["scope_gap", "direction"]
        assert evidence.requests[0].selected_candidate is None
        assert narrative.discoveries == 2
        for _ in range(3):
            approve_gate(client, run_id)
        assert wait_for(client, run_id, "published").state.research_rounds_started == 2


def test_scope_loop_stops_for_human_without_resetting_rounds(tmp_path: Path) -> None:
    evidence = BranchEvidence()
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=BranchNarrative("scope_limit"))
    ) as client:
        run_id = create_run(client)
        run = stopped(client, run_id, "needs_review")
        assert run.state.node == "discover_story"
        assert run.state.research_rounds_started == 2 and len(evidence.requests) == 2
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=run.state.revision, reason="Cannot reset rounds"),
        )
        assert response.status_code == 409


def test_draft_gap_requires_fresh_evidence_review_before_redraft(tmp_path: Path) -> None:
    evidence, narrative = BranchEvidence(), BranchNarrative("draft_gap")
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=narrative)
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        first = wait_for(client, run_id, "waiting_review")
        approve_gate(client, run_id)
        second = wait_for(client, run_id, "waiting_review")
        assert second.state.node == "evidence_review" and second.state.research_rounds_started == 2
        assert second.state.pending_review_id != first.state.pending_review_id
        assert narrative.drafts == 1 and second.state.approved_route_ref is None
        approve_gate(client, run_id)
        assert wait_for(client, run_id, "waiting_review").state.node == "narrative_review"
        assert narrative.drafts == 2
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        wait_for(client, run_id, "published")


def test_module_changes_are_revised_without_granting_human_approval(tmp_path: Path) -> None:
    narrative = BranchNarrative("change")
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        run = wait_for(client, run_id, "waiting_review")
        assert run.state.node == "narrative_review" and run.state.narrative_revisions_started == 1
        assert len(narrative.revisions) == 1
        assert not any(d.gate == "narrative" for d in run.review_decisions)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        wait_for(client, run_id, "published")


def test_repeated_changes_stop_after_two_automatic_revisions(tmp_path: Path) -> None:
    narrative = BranchNarrative("change")
    narrative.keep_changing = True
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        run = stopped(client, run_id, "needs_review")
        assert run.state.narrative_revisions_started == 2 and len(narrative.revisions) == 2


@pytest.mark.parametrize("gate", ["evidence", "narrative"])
def test_human_changes_route_to_responsible_module(tmp_path: Path, gate: str) -> None:
    evidence, narrative = BranchEvidence(), BranchNarrative()
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=narrative)
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        if gate == "narrative":
            approve_gate(client, run_id)
        old = reject_gate(client, run_id)
        new = wait_for(client, run_id, "waiting_review")
        assert new.state.pending_review_id != old.state.pending_review_id
        assert new.state.node == ("evidence_review" if gate == "evidence" else "narrative_review")
        assert new.state.research_rounds_started == (2 if gate == "evidence" else 1)
        assert new.state.narrative_revisions_started == (1 if gate == "narrative" else 0)
        remaining = 3 if gate == "evidence" else 2
        for _ in range(remaining):
            approve_gate(client, run_id)
        wait_for(client, run_id, "published")


def test_professional_review_can_revise_and_returns_to_existing_human_gate(tmp_path: Path) -> None:
    narrative = BranchNarrative()
    narrative.review_changes_once = True
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        old = action(client, run_id, "review")
        new = wait_for(client, run_id, "waiting_review")
        assert new.state.pending_review_id != old.state.pending_review_id
        assert narrative.reviews == 2 and len(narrative.revisions) == 1
        assert not any(d.gate == "narrative" for d in new.review_decisions)
        assert any("professional-review" in a.reference.artifact_id for a in new.artifacts)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        wait_for(client, run_id, "published")


def test_automatic_revision_enforces_human_field_locks(tmp_path: Path) -> None:
    narrative = BranchNarrative()
    narrative.break_lock = True
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        run = wait_for(client, run_id, "waiting_review")
        response = client.post(
            "/api/v1/runs/" + run_id + "/locks",
            headers=headers(),
            json=dict(
                expected_revision=run.state.revision,
                json_pointers=["/package/game/locales/0/entries/0/text"],
                reason="Human protects wording",
            ),
        )
        assert response.status_code == 200
        old_hash = run.state.narrative_ref
        action(client, run_id, "revise")
        failed = stopped(client, run_id, "failed")
        assert (
            failed.state.last_error is not None and failed.state.last_error.code == "FIELD_LOCKED"
        )
        assert failed.state.narrative_ref == old_hash
        assert len(narrative.revisions) == 1


def test_blocked_result_can_retry_explicitly_without_resetting_research_round(
    tmp_path: Path,
) -> None:
    evidence = BranchEvidence()
    evidence.block_once = True
    with TestClient(create_app(settings(tmp_path), evidence=evidence)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        run = stopped(client, run_id, "blocked")
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=run.state.revision, reason="Source available again"),
        )
        assert response.status_code == 202
        run = wait_for(client, run_id, "waiting_review")
        assert run.state.research_rounds_started == 1 and len(evidence.requests) == 2


def test_no_feasible_suggestion_cannot_end_project_without_policy_proof(tmp_path: Path) -> None:
    with TestClient(
        create_app(settings(tmp_path), narrative=BranchNarrative("no_feasible"))
    ) as client:
        run_id = create_run(client)
        run = stopped(client, run_id, "needs_review")
        assert run.state.node == "discover_story" and run.state.research_rounds_started == 0


def test_index_gap_can_research_without_a_story_direction(tmp_path: Path) -> None:
    evidence = BranchEvidence()
    evidence.index_gap = True
    with TestClient(create_app(settings(tmp_path), evidence=evidence)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        run = wait_for(client, run_id, "waiting_review")
        assert run.state.node == "evidence_review"
        assert run.state.research_rounds_started == 2
        assert evidence.requests[0].selected_candidate is None


def test_revision_can_request_evidence_and_continue_after_new_approval(tmp_path: Path) -> None:
    narrative = BranchNarrative()
    narrative.revision_gap_once = True
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        old = action(client, run_id, "revise")
        evidence = wait_for(client, run_id, "waiting_review")
        assert evidence.state.node == "evidence_review"
        assert evidence.state.research_rounds_started == 2
        assert evidence.state.approved_route_ref is None
        approve_gate(client, run_id)
        revised = wait_for(client, run_id, "waiting_review")
        assert revised.state.node == "narrative_review"
        assert revised.state.narrative_revisions_started == 2
        assert revised.state.narrative_ref != old.state.narrative_ref
        assert len(narrative.revisions) == 2
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        wait_for(client, run_id, "published")


@pytest.mark.parametrize("kind", ["research", "revision"])
def test_committed_branch_result_replays_after_restart_without_another_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from pastport.adapters.database import EditorialDatabase
    from pastport.application.reliability import UsageSettlement

    evidence, narrative = (
        BranchEvidence(),
        BranchNarrative("change" if kind == "revision" else "normal"),
    )
    original = EditorialDatabase.finish_operation
    injected = False

    def finish(
        self: EditorialDatabase,
        operation_id: str,
        result_json: str,
        active_milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        nonlocal injected
        original(self, operation_id, result_json, active_milliseconds, settlement)
        marker = "research-1-0" if kind == "research" else "revision-1"
        if not injected and marker in operation_id:
            injected = True
            raise RuntimeError("Crash after durable response and usage settlement")

    monkeypatch.setattr(EditorialDatabase, "finish_operation", finish)
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=narrative)
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        if kind == "revision":
            approve_gate(client, run_id)
        run = stopped(client, run_id, "failed")
        assert injected
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=narrative)
    ) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=run.state.revision, reason="Recover durable result"),
        )
        assert response.status_code == 202
        ready = wait_for(client, run_id, "waiting_review")
        assert ready.state.research_rounds_started == 1 and len(evidence.requests) == 1
        if kind == "revision":
            assert ready.state.narrative_revisions_started == 1 and len(narrative.revisions) == 1
        entries = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()[
            "entries"
        ]
        matching = [entry for entry in entries if marker_for(kind) in entry["operation_id"]]
        assert len(matching) == 1 and matching[0]["state"] == "settled"


def marker_for(kind: str) -> str:
    return "research-1-0" if kind == "research" else "revision-1"


def test_professional_report_cannot_reference_a_stale_story(tmp_path: Path) -> None:
    narrative = BranchNarrative()
    narrative.stale_review = True
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        action(client, run_id, "review")
        run = stopped(client, run_id, "needs_review")
        assert run.state.last_error is not None and run.state.last_error.code == "REVIEW_STALE"
        assert not any(d.gate == "narrative" for d in run.review_decisions)


def test_explicit_rejection_cannot_be_resumed_as_approval(tmp_path: Path) -> None:
    narrative = BranchNarrative()
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        reject_gate(client, run_id, reject=True)
        run = record(client, run_id)
        assert run.state.status == "needs_changes" and not narrative.revisions
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=run.state.revision, reason="Cannot undo rejection"),
        )
        assert response.status_code == 409


@pytest.mark.parametrize("kind", ["review", "revise"])
def test_unknown_revision_targets_do_not_mutate_the_run(tmp_path: Path, kind: str) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        run = wait_for(client, run_id, "waiting_review")
        response = client.post(
            "/api/v1/runs/" + run_id + "/narrative-requests",
            headers=headers(),
            json=dict(
                expected_revision=run.state.revision,
                action=kind,
                feedback="Invalid target",
                target_ids=["another-project-story"],
            ),
        )
        assert response.status_code == 409 and response.json()["code"] == "REVISION_REQUEST_INVALID"
        assert record(client, run_id).state == run.state


@pytest.mark.parametrize("owner", ["evidence", "narrative", "assembly"])
def test_publication_changes_require_and_follow_an_explicit_owner(
    tmp_path: Path, owner: str
) -> None:
    narrative = BranchNarrative()
    with TestClient(create_app(settings(tmp_path), narrative=narrative)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        run = wait_for(client, run_id, "waiting_review")
        pending = next(
            r for r in run.review_requests if r.request_id == run.state.pending_review_id
        )
        body = dict(
            expected_revision=run.state.revision,
            request_id=pending.request_id,
            decisions=[
                dict(
                    target_id=t.target_id,
                    target_version=t.version,
                    target_hash=t.sha256,
                    decision="changes_requested",
                    reason="Rework the publication package",
                )
                for t in pending.targets
            ],
        )
        refused = client.post(
            "/api/v1/runs/" + run_id + "/review-decisions", headers=headers(), json=body
        )
        assert refused.status_code == 422 and record(client, run_id).state == run.state
        body["rework_owner"] = owner
        accepted = client.post(
            "/api/v1/runs/" + run_id + "/review-decisions", headers=headers(), json=body
        )
        assert accepted.status_code == 202, accepted.text
        for _ in range(3 if owner == "evidence" else 2 if owner == "narrative" else 1):
            approve_gate(client, run_id)
        final = wait_for(client, run_id, "published")
        assert final.state.research_rounds_started == (2 if owner == "evidence" else 1)
        assert final.state.narrative_revisions_started == (0 if owner == "assembly" else 1)


def test_validator_narrative_issue_returns_to_revision_and_fresh_review(tmp_path: Path) -> None:
    from pastport.adapters.assembly import PackageAssembler
    from pastport.adapters.resources import LocalResourceReader
    from pastport.domain.common import ValidationIssue
    from pastport.domain.modules import PackageValidationRequest
    from pastport.domain.packages import ValidationReport

    class CheckOnce(PackageAssembler):
        checks = 0

        def validate(self, request: PackageValidationRequest) -> ValidationReport:
            report = super().validate(request)
            self.checks += 1
            if self.checks == 1:
                return updated(
                    report,
                    issues=(
                        ValidationIssue(
                            code="CONSEQUENCE_MISSING",
                            severity="blocking",
                            owner="narrative",
                            artifact_id=None,
                            json_pointer="",
                            message="Consequence is missing",
                            remediation="Revise the story and repeat human review",
                        ),
                    ),
                )
            return report

    narrative = BranchNarrative()
    with TestClient(
        create_app(
            settings(tmp_path),
            narrative=narrative,
            validator=CheckOnce(LocalResourceReader(FIXTURES, fixture_projects=True)),
        )
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        review = wait_for(client, run_id, "waiting_review")
        assert (
            review.state.node == "narrative_review"
            and review.state.narrative_revisions_started == 1
        )
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        wait_for(client, run_id, "published")


def test_no_feasible_terminal_requires_exhausted_rounds_and_current_candidate_comparison(
    tmp_path: Path,
) -> None:
    class ExhaustedNarrative(BranchNarrative):
        async def discover(
            self, request: DiscoverRequest, context: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            result = await super().discover(request, context)
            if self.discoveries <= 2:
                return updated(
                    result,
                    outcome="research_required",
                    payload=None,
                    evidence_requests=(gap(context, request.index.sites[0].site_id),),
                )
            assert result.payload is not None
            candidates = tuple(
                updated(c, blocking_gaps=("Known scope cannot support the required premise",))
                for c in result.payload.candidates
            )
            return updated(
                result,
                outcome="no_feasible_story",
                payload=updated(result.payload, candidates=candidates),
                reason="All compared directions remain infeasible after two complete scope rounds",
            )

    evidence = BranchEvidence()
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=ExhaustedNarrative())
    ) as client:
        run_id = create_run(client)
        run = stopped(client, run_id, "no_feasible_story")
        assert run.state.research_rounds_started == 2 and len(evidence.requests) == 2
        assert run.selected_candidate is None
        assert any("feasibility" in a.reference.artifact_id for a in run.artifacts)


def test_frozen_multi_question_round_resumes_only_its_unfinished_question(tmp_path: Path) -> None:
    from pastport.application.models import ServiceError

    class TwoQuestions(BranchNarrative):
        async def discover(
            self, request: DiscoverRequest, context: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            result = await super().discover(request, context)
            if self.discoveries == 1:
                question = gap(context, request.index.sites[0].site_id)
                return updated(
                    result,
                    outcome="research_required",
                    payload=None,
                    evidence_requests=(
                        question,
                        updated(
                            question,
                            request_id=question.request_id + "-second",
                            question="Verify the registered structure identity",
                        ),
                    ),
                )
            return result

    class RetrySecond(BranchEvidence):
        def __init__(self) -> None:
            super().__init__()
            self.attempted: list[str] = []

        async def research(
            self, request: ResearchRequest, context: ExecutionContext
        ) -> ModuleResult[EvidenceFindings]:
            self.attempted.append(request.evidence_request.request_id)
            if len(self.attempted) == 2:
                raise ServiceError(
                    "LOCAL_RESEARCH_TEMPORARY", "Registered local source unavailable"
                )
            return await super().research(request, context)

    evidence = RetrySecond()
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=TwoQuestions())
    ) as client:
        run_id = create_run(client)
        run = stopped(client, run_id, "failed")
        manifest = run.control.research_rounds[0]
        assert len(manifest.requests) == 2 and len(manifest.findings) == 1
        resumed = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=run.state.revision, reason="Retry unfinished local source"),
        )
        assert resumed.status_code == 202
        confirm_direction(client, run_id)
        ready = wait_for(client, run_id, "waiting_review")
        assert ready.state.research_rounds_started == 2
        assert ready.control.research_rounds[0].requests == manifest.requests
        assert len(ready.control.research_rounds[0].findings) == 2
        assert evidence.attempted[:3] == [
            manifest.requests[0].request_id,
            manifest.requests[1].request_id,
            manifest.requests[1].request_id,
        ]


@pytest.mark.parametrize("invalid", ["project", "target"])
def test_research_cannot_escape_its_registered_project_scope(tmp_path: Path, invalid: str) -> None:
    class InvalidResearch(BranchNarrative):
        async def discover(
            self, request: DiscoverRequest, context: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            result = await super().discover(request, context)
            question = gap(context, request.index.sites[0].site_id)
            question = (
                updated(question, project_id="other-project")
                if invalid == "project"
                else updated(question, affected_ids=("unknown-site",))
            )
            return updated(
                result, outcome="research_required", payload=None, evidence_requests=(question,)
            )

    evidence = BranchEvidence()
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=InvalidResearch())
    ) as client:
        run_id = create_run(client)
        failed = stopped(client, run_id, "failed")
        assert failed.state.last_error is not None
        assert failed.state.last_error.code == (
            "PROJECT_MISMATCH" if invalid == "project" else "RESEARCH_SCOPE_INVALID"
        )
        assert failed.state.research_rounds_started == 0 and not evidence.requests


def test_legacy_graph_run_is_refused_before_any_new_module_call(tmp_path: Path) -> None:
    from pastport.adapters.database import EditorialDatabase
    from pastport.application.models import LocalExecutionPolicy

    evidence, narrative = BranchEvidence(), BranchNarrative()
    with TestClient(
        create_app(settings(tmp_path), evidence=evidence, narrative=narrative)
    ) as client:
        run_id = create_run(client)
        run = wait_for(client, run_id, "needs_review")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        legacy_policy = updated(
            LocalExecutionPolicy(environment="test"), version="local-1", graph_version="editorial-1"
        )
        legacy = updated(
            run,
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                status="running",
                graph_version="editorial-1",
                policy_ref=updated(
                    run.state.policy_ref,
                    content_version="local-1",
                    sha256=CanonicalSerializer.digest(legacy_policy),
                ),
            ),
        )
        database.save(
            legacy, run.state.revision, "Simulate a legacy run requiring migration", enqueue=True
        )
        blocked = stopped(client, run_id, "blocked")
        assert (
            blocked.state.last_error is not None
            and blocked.state.last_error.code == "RUN_VERSION_UNSUPPORTED"
        )
        assert narrative.discoveries == 1 and not evidence.requests
