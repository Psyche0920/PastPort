"""Application-owned legal routes and cumulative research/revision limits."""

from typing import Literal

from pastport.application.models import RunRecord, ServiceError
from pastport.application.story_editing import story_target_ids
from pastport.application.updates import updated
from pastport.domain.common import EvidenceRequest
from pastport.domain.evidence import SourceIndexDraft
from pastport.domain.modules import CandidateSetDraft, NarrativeDraft, RevisionRequest
from pastport.domain.workflow import WorkflowError
from pastport.ports.editorial import EditorialRepository


class WorkflowRouter:
    def __init__(self, database: EditorialRepository) -> None:
        self.database = database

    def stop(
        self,
        run: RunRecord,
        code: str,
        reason: str,
        status: Literal["needs_review", "blocked", "needs_changes"] = "needs_review",
    ) -> None:
        self.database.save(
            updated(
                run,
                state=updated(
                    run.state,
                    revision=run.state.revision + 1,
                    status=status,
                    last_error=WorkflowError(
                        code=code,
                        message=reason,
                        retryable=status == "blocked",
                        owner="workflow",
                        field_path="",
                    ),
                ),
            ),
            run.state.revision,
            code,
        )

    def no_feasible(
        self, run: RunRecord, comparison: CandidateSetDraft | None, reason: str
    ) -> None:
        rounds = run.control.research_rounds
        index_ref = next(
            (
                a.reference
                for a in reversed(run.artifacts)
                if a.reference.artifact_id == run.state.run_id + ":index"
            ),
            None,
        )
        verified = (
            run.selected_candidate is None
            and run.state.research_rounds_started == 2
            and len(rounds) == 2
            and all(r.completed and len(r.findings) == len(r.requests) for r in rounds)
            and comparison is not None
            and bool(comparison.candidates)
            and all(c.blocking_gaps and index_ref in c.source_refs for c in comparison.candidates)
        )
        if not verified:
            self.stop(run, "FEASIBILITY_REVIEW_REQUIRED", reason)
            return
        self.database.save(
            updated(
                run,
                state=updated(
                    run.state,
                    revision=run.state.revision + 1,
                    status="no_feasible_story",
                    pending_request_id=None,
                    last_error=WorkflowError(
                        code="NO_FEASIBLE_STORY",
                        message=reason,
                        retryable=False,
                        owner="workflow",
                        field_path="",
                    ),
                ),
            ),
            run.state.revision,
            "Candidate comparison and exhausted research policy verified",
        )

    def research(
        self,
        run: RunRecord,
        requests: tuple[EvidenceRequest, ...],
        return_action: Literal["discover", "draft", "revise"],
    ) -> None:
        self.check_research(run, requests)
        if run.state.research_rounds_started >= 2:
            self.stop(run, "RESEARCH_LIMIT", "The two shared research rounds are exhausted")
            return
        self.database.save(
            self.research_plan(run, requests, return_action),
            run.state.revision,
            "Evidence request queued",
        )

    @staticmethod
    def check_research(run: RunRecord, requests: tuple[EvidenceRequest, ...]) -> None:
        if (
            not requests
            or len(requests) > 8
            or len({r.request_id for r in requests}) != len(requests)
        ):
            raise ServiceError("RESEARCH_REQUEST_INVALID", "A round needs 1 to 8 unique questions")
        index_artifact = next(
            item
            for item in reversed(run.artifacts)
            if item.reference.artifact_id == run.state.run_id + ":index"
        )
        index = SourceIndexDraft.model_validate_json(index_artifact.payload_json)
        source_ids = {item.source_id for item in index.sources}
        known = source_ids | {item.site_id for item in index.sites}
        known |= {item.claim_id for item in index.candidate_claims}
        known |= {item.asset_id for item in index.candidate_assets}
        selected = run.selected_candidate
        if selected:
            known.add(selected.candidate_id)
            known |= {a.reference.artifact_id for a in run.artifacts}
        # Story references may identify the scene/task needing direction-specific premises.
        if selected:
            for artifact in reversed(run.artifacts):
                if artifact.reference.artifact_id == run.state.run_id + ":draft":
                    game = NarrativeDraft.model_validate_json(artifact.payload_json).package.game
                    known |= {game.chapter_id}
                    known |= {scene.scene_id for scene in game.scenes}
                    known |= {task.task_id for scene in game.scenes for task in scene.tasks}
                    break
        for request in requests:
            if (
                request.project_id != run.state.project_id
                or not set(request.existing_source_ids) <= source_ids
                or not request.affected_ids
                or not set(request.affected_ids) <= known
            ):
                raise ServiceError(
                    "RESEARCH_SCOPE_INVALID", "Research must name registered project targets"
                )
            if selected is None:
                if request.purpose != "scope_gap" or request.candidate_id is not None:
                    raise ServiceError(
                        "RESEARCH_SCOPE_INVALID", "Unselected research requires scope_gap"
                    )
            elif request.purpose != "direction" or request.candidate_id != selected.candidate_id:
                raise ServiceError(
                    "RESEARCH_SCOPE_INVALID", "Research must retain the selected direction"
                )

    @staticmethod
    def research_plan(
        run: RunRecord,
        requests: tuple[EvidenceRequest, ...],
        return_action: Literal["discover", "draft", "revise"],
    ) -> RunRecord:
        return updated(
            run,
            control=updated(
                run.control, pending_research=requests, research_return_action=return_action
            ),
            review_requests=(),
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                node="research_evidence",
                status="running",
                pending_request_id=requests[0].request_id,
                pending_review_id=None,
                approved_route_ref=None,
                runtime_ref=None,
                last_error=None,
            ),
        )

    def revision(self, run: RunRecord, request: RevisionRequest) -> None:
        self.check_revision(run, request)
        if run.state.narrative_revisions_started >= 2:
            self.stop(run, "REVISION_LIMIT", "The two narrative revision rounds are exhausted")
            return
        self.database.save(
            self.revision_plan(run, request), run.state.revision, "Narrative revision requested"
        )

    @staticmethod
    def check_revision(run: RunRecord, request: RevisionRequest) -> None:
        artifact = next(
            (
                a
                for a in reversed(run.artifacts)
                if a.reference.artifact_id == run.state.run_id + ":draft"
            ),
            None,
        )
        if artifact is None:
            raise ServiceError("REVISION_REQUEST_INVALID", "Revision requires a concrete draft")
        draft = NarrativeDraft.model_validate_json(artifact.payload_json)
        targets = story_target_ids(draft) | {run.state.run_id + ":narrative"}
        if not set(request.target_ids) <= targets or request.locked_fields != run.locked_fields:
            raise ServiceError(
                "REVISION_REQUEST_INVALID",
                "Revision targets or locks differ from the current story",
            )

    @staticmethod
    def revision_plan(run: RunRecord, request: RevisionRequest) -> RunRecord:
        WorkflowRouter.check_revision(run, request)
        return updated(
            run,
            control=updated(run.control, action="revise", revision_request=request),
            review_requests=tuple(r for r in run.review_requests if r.gate == "evidence"),
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                node="draft_narrative",
                status="running",
                pending_review_id=None,
                pending_request_id=request.request_id,
                runtime_ref=None,
                dirty_target_ids=tuple(sorted(set(request.target_ids))),
                last_error=None,
            ),
        )

    @staticmethod
    def review_plan(run: RunRecord, request_id: str) -> RunRecord:
        return updated(
            run,
            control=updated(
                run.control, action="review", professional_review=True, review_request_id=request_id
            ),
            review_requests=tuple(r for r in run.review_requests if r.gate == "evidence"),
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                node="draft_narrative",
                status="running",
                pending_review_id=None,
                pending_request_id=request_id,
                runtime_ref=None,
                last_error=None,
            ),
        )

    @staticmethod
    def research_question(
        run: RunRecord, reason: str, affected_ids: tuple[str, ...]
    ) -> EvidenceRequest:
        selected = run.selected_candidate
        if selected is None:
            raise ServiceError(
                "SELECTION_MISSING", "Direction research needs a confirmed candidate"
            )
        return EvidenceRequest(
            request_id="research-" + str(run.state.revision),
            project_id=run.state.project_id,
            purpose="direction",
            candidate_id=selected.candidate_id,
            question=reason,
            reason=reason,
            affected_ids=affected_ids or (selected.candidate_id,),
            existing_source_ids=(),
            required_evidence=(reason,),
        )
