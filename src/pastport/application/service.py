"""Application operations enforce identity, review authority and optimistic versions."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pastport.application.execution_models import ExecutionBinding
from pastport.application.models import (
    Actor,
    CreateProject,
    CreateRun,
    LocalExecutionPolicy,
    ProjectRecord,
    RequestReceipt,
    ReviewRequest,
    RunCommand,
    RunRecord,
    SelectCandidate,
    ServiceError,
    SetLocks,
    StoredArtifact,
    SubmitReview,
    SubmitRevision,
)
from pastport.application.reliability import ReviewAuthority, ReviewRevocation, RevokeReview
from pastport.application.routing import WorkflowRouter
from pastport.application.story_editing import story_field_hash
from pastport.application.updates import updated
from pastport.application.workflow_control import RequestNarrativeAction
from pastport.domain.common import ArtifactRef, CanonicalSerializer, ReviewDecision
from pastport.domain.modules import (
    CandidateSetDraft,
    LockedField,
    NarrativeDraft,
    RevisionRequest,
    SelectedCandidate,
)
from pastport.domain.packages import ReviewTarget
from pastport.domain.workflow import WorkflowState
from pastport.ports.editorial import EditorialRepository


class EditorialService:
    def __init__(
        self,
        database: EditorialRepository,
        environment: str,
        authority: ReviewAuthority,
        policy: LocalExecutionPolicy | None = None,
        execution_binding: ExecutionBinding | None = None,
    ) -> None:
        self.database = database
        self.authority = authority
        self.environment = environment
        self.execution_binding = execution_binding
        self.policy = (
            policy
            if policy is not None
            else LocalExecutionPolicy(environment="test" if environment == "test" else "production")
        )

    def policy_reference(self, project_id: str) -> ArtifactRef:
        return ArtifactRef(
            artifact_id="local-policy",
            project_id=project_id,
            kind="policy",
            schema_version="0.1.0",
            content_version=self.policy.version,
            sha256=CanonicalSerializer.digest(self.policy),
        )

    @staticmethod
    def authorize(actor: Actor, project_id: str, role: str | None = None) -> None:
        if actor.project_ids is not None and project_id not in actor.project_ids:
            raise ServiceError("PROJECT_FORBIDDEN", "You cannot access this project", 403)
        if role is not None and role not in actor.roles:
            raise ServiceError("ROLE_FORBIDDEN", "Your account cannot perform this action", 403)

    def project(self, project_id: str, actor: Actor) -> ProjectRecord:
        self.authorize(actor, project_id)
        return self.database.project(project_id)

    def run(self, run_id: str, actor: Actor) -> RunRecord:
        run = self.database.run(run_id)
        self.authorize(actor, run.state.project_id)
        return run

    def create_project(
        self, request: CreateProject, actor: Actor, receipt: RequestReceipt
    ) -> ProjectRecord:
        project_id = request.requirements.project_id
        self.authorize(actor, project_id, "editor")
        return self.database.create_project(
            ProjectRecord(
                project_id=project_id,
                name=request.name,
                provider=request.provider,
                folder_id=request.folder_id,
                requirements=request.requirements,
                created_by=actor.actor_id,
            ),
            receipt,
        )

    def create_run(
        self, project_id: str, request: CreateRun, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        self.authorize(actor, project_id, "editor")
        project = self.database.project(project_id)
        if request.policy_ref != self.policy_reference(project_id):
            raise ServiceError("POLICY_INVALID", "Policy must belong to the current project")
        if self.environment == "test" and project.requirements.distribution_scope == "public":
            raise ServiceError(
                "TEST_PUBLICATION_FORBIDDEN", "Test runs cannot create public content"
            )
        run_id = str(uuid4())
        state = WorkflowState(
            schema_version="0.1.0",
            project_id=project_id,
            run_id=run_id,
            graph_version=self.policy.graph_version,
            policy_ref=request.policy_ref,
            revision=0,
            node="register_project",
            status="queued",
            index_ref=None,
            evidence_ref=None,
            narrative_ref=None,
            runtime_ref=None,
            approved_route_ref=None,
            selected_candidate_id=None,
            pending_review_id=None,
            pending_request_id=None,
            research_rounds_started=0,
            narrative_revisions_started=0,
            budget_id="budget-" + run_id,
            usage_ledger_id="ledger-" + run_id,
            dirty_target_ids=(),
            last_error=None,
        )
        artifacts: tuple[StoredArtifact, ...] = ()
        if self.execution_binding is not None:
            binding = self.execution_binding
            binding_ref = ArtifactRef(
                artifact_id=run_id + ":execution-binding",
                project_id=project_id,
                kind="model_config",
                schema_version="0.1.0",
                content_version=self.policy.version,
                sha256=CanonicalSerializer.digest(binding),
            )
            artifacts = (
                StoredArtifact(reference=binding_ref, payload_json=binding.model_dump_json()),
            )
        run = RunRecord(
            state=state,
            budget_policy=request.budget_policy,
            artifacts=artifacts,
            review_requests=(),
            review_decisions=(),
            selected_candidate=None,
            environment="test" if self.environment == "test" else "production",
            created_by=actor.actor_id,
            current_release_id=None,
            expected_old_release=self.database.current_release(project_id),
        )
        self.database.create_run(run, receipt)
        return run

    @staticmethod
    def require_revision(run: RunRecord, expected_revision: int) -> None:
        if run.state.revision != expected_revision:
            raise ServiceError("STATE_STALE", "Run changed; reload before retrying")

    def select_candidate(
        self, run_id: str, request: SelectCandidate, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.authorize(actor, run.state.project_id, "narrative")
        self.authority.actor(actor.actor_id, run.state.project_id, "narrative")
        self.require_revision(run, request.expected_revision)
        if run.state.node != "select_candidate" or run.state.status != "needs_review":
            raise ServiceError("SELECTION_NOT_PENDING", "No direction selection is pending")
        artifact = next(
            item for item in reversed(run.artifacts) if item.reference.kind == "candidate_set"
        )
        if artifact.reference.sha256 != request.candidate_set_hash:
            raise ServiceError("SELECTION_STALE", "Candidate comparison changed")
        candidates = CandidateSetDraft.model_validate_json(artifact.payload_json)
        candidate = next(
            (item for item in candidates.candidates if item.candidate_id == request.candidate_id),
            None,
        )
        if candidate is None or candidate.blocking_gaps:
            raise ServiceError("CANDIDATE_INVALID", "Candidate is missing or has blocking gaps")
        requirements = self.database.project(run.state.project_id).requirements
        selection = SelectedCandidate(
            project_id=run.state.project_id,
            candidate_set_ref=artifact.reference,
            candidate_id=request.candidate_id,
            requirements_ref=CanonicalSerializer.reference(
                requirements, "requirements-" + run.state.project_id, "requirements"
            ),
            policy_ref=run.state.policy_ref,
            actor_id=actor.actor_id,
            reason=request.reason,
        )
        state = updated(
            run.state,
            revision=run.state.revision + 1,
            status="running",
            selected_candidate_id=request.candidate_id,
        )
        result = updated(run, state=state, selected_candidate=selection)
        self.database.save(
            result, run.state.revision, "Direction confirmed", enqueue=True, receipt=receipt
        )
        return result

    def submit_review(
        self, run_id: str, request: SubmitReview, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.require_revision(run, request.expected_revision)
        pending = next(
            (item for item in run.review_requests if item.request_id == request.request_id), None
        )
        if (
            pending is None
            or run.state.pending_review_id != pending.request_id
            or run.state.status != "waiting_review"
        ):
            raise ServiceError("REVIEW_STALE", "This review is no longer pending")
        required_role = "publisher" if pending.gate == "publication" else pending.gate
        self.authorize(actor, run.state.project_id, required_role)
        self.authority.actor(actor.actor_id, run.state.project_id, required_role)
        expected = {(item.target_id, item.version, item.sha256) for item in pending.targets}
        supplied = {
            (item.target_id, item.target_version, item.target_hash) for item in request.decisions
        }
        if expected != supplied or len(supplied) != len(request.decisions):
            raise ServiceError(
                "REVIEW_STALE", "Review must cover the exact current target versions"
            )
        decisions = tuple(
            ReviewDecision(
                decision_id=str(uuid4()),
                gate=pending.gate,
                target_id=item.target_id,
                target_version=item.target_version,
                target_hash=item.target_hash,
                decision=item.decision,
                reason=item.reason,
                actor_id=actor.actor_id,
                created_at=datetime.now(UTC),
                environment=run.environment,
            )
            for item in request.decisions
        )
        approved = all(item.decision == "approved" for item in decisions)
        result = updated(
            run,
            review_decisions=(*run.review_decisions, *decisions),
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                status="running" if approved else "needs_changes",
                pending_review_id=None if approved else pending.request_id,
            ),
        )
        automatic = not approved and all(item.decision != "rejected" for item in decisions)
        if automatic and (
            pending.gate == "narrative"
            or pending.gate == "publication"
            and request.rework_owner == "narrative"
        ):
            if run.state.narrative_revisions_started >= 2:
                result = updated(
                    result,
                    state=updated(result.state, status="needs_review", pending_review_id=None),
                )
            else:
                feedback = "; ".join(
                    item.reason for item in decisions if item.decision != "approved"
                )[:10000]
                result = WorkflowRouter.revision_plan(
                    run,
                    RevisionRequest(
                        request_id="human-revision-" + str(run.state.revision),
                        feedback=feedback,
                        target_ids=(run.state.run_id + ":narrative",)
                        if pending.gate == "publication"
                        else tuple(
                            item.target_id for item in decisions if item.decision != "approved"
                        ),
                        reason=feedback,
                        locked_fields=run.locked_fields,
                    ),
                )
                result = updated(result, review_decisions=(*run.review_decisions, *decisions))
        elif automatic and (
            pending.gate == "evidence"
            or pending.gate == "publication"
            and request.rework_owner == "evidence"
        ):
            if run.state.research_rounds_started >= 2:
                result = updated(
                    result,
                    state=updated(result.state, status="needs_review", pending_review_id=None),
                )
            else:
                feedback = "; ".join(
                    item.reason for item in decisions if item.decision != "approved"
                )[:10000]
                question = WorkflowRouter.research_question(
                    run,
                    feedback,
                    tuple(item.target_id for item in decisions if item.decision != "approved"),
                )
                WorkflowRouter.check_research(run, (question,))
                continuation: Literal["draft", "revise"] = "draft"
                if any(
                    a.reference.artifact_id == run.state.run_id + ":draft" for a in run.artifacts
                ):
                    continuation = "revise"
                    run = updated(
                        run,
                        control=updated(
                            run.control,
                            revision_request=RevisionRequest(
                                request_id="evidence-feedback-" + str(run.state.revision),
                                feedback=feedback,
                                target_ids=(run.state.run_id + ":narrative",),
                                reason=feedback,
                                locked_fields=run.locked_fields,
                            ),
                        ),
                    )
                result = WorkflowRouter.research_plan(run, (question,), continuation)
                result = updated(result, review_decisions=(*run.review_decisions, *decisions))
        elif automatic and pending.gate == "publication":
            if request.rework_owner != "assembly":
                raise ServiceError(
                    "REWORK_OWNER_REQUIRED",
                    "Publication changes require evidence, narrative or assembly rework_owner",
                    422,
                )
            result = updated(
                result,
                review_requests=tuple(r for r in run.review_requests if r.gate != "publication"),
                state=updated(
                    result.state,
                    node="assemble_package",
                    status="running",
                    pending_review_id=None,
                    runtime_ref=None,
                ),
            )
        self.database.save_review(
            result, run.state.revision, receipt, enqueue=result.state.status == "running"
        )
        return result

    def request_narrative_action(
        self, run_id: str, request: RequestNarrativeAction, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.authorize(actor, run.state.project_id, "narrative")
        self.authority.actor(actor.actor_id, run.state.project_id, "narrative")
        self.require_revision(run, request.expected_revision)
        self._editable_story(run)
        request_id = "human-action-" + str(run.state.revision)
        WorkflowRouter.check_revision(
            run,
            RevisionRequest(
                request_id=request_id,
                feedback=request.feedback,
                target_ids=request.target_ids,
                reason=request.feedback,
                locked_fields=run.locked_fields,
            ),
        )
        if request.action == "revise":
            if run.state.narrative_revisions_started >= 2:
                raise ServiceError(
                    "REVISION_LIMIT", "The two narrative revision rounds are exhausted"
                )
            result = WorkflowRouter.revision_plan(
                run,
                RevisionRequest(
                    request_id=request_id,
                    feedback=request.feedback,
                    target_ids=request.target_ids,
                    reason=request.feedback,
                    locked_fields=run.locked_fields,
                ),
            )
        else:
            result = WorkflowRouter.review_plan(run, request_id)
        self.database.save(
            result, run.state.revision, "Narrative action queued", enqueue=True, receipt=receipt
        )
        return result

    def cancel(
        self, run_id: str, request: RunCommand, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.authorize(actor, run.state.project_id, "editor")
        self.require_revision(run, request.expected_revision)
        if run.state.status in ("published", "cancelled", "no_feasible_story"):
            raise ServiceError("RUN_TERMINAL", "This run has already ended")
        result = updated(
            run, state=updated(run.state, revision=run.state.revision + 1, status="cancelled")
        )
        self.database.save(
            result, run.state.revision, "Run cancelled", enqueue=True, receipt=receipt
        )
        return result

    def resume(
        self, run_id: str, request: RunCommand, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.authorize(actor, run.state.project_id, "editor")
        self.require_revision(run, request.expected_revision)
        if run.state.status not in ("blocked", "failed"):
            raise ServiceError(
                "RESUME_NOT_ALLOWED",
                "Resume cannot grant approval, reset budgets or undo rejection",
            )
        control = run.control
        if run.state.last_error is not None and run.state.last_error.code == "MODULE_BLOCKED":
            control = updated(control, retry_generation=control.retry_generation + 1)
        result = updated(
            run,
            control=control,
            state=updated(
                run.state, revision=run.state.revision + 1, status="running", last_error=None
            ),
        )
        self.database.save(result, run.state.revision, "Run resumed", enqueue=True, receipt=receipt)
        return result

    def set_locks(
        self, run_id: str, request: "SetLocks", actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.authorize(actor, run.state.project_id, "narrative")
        self.require_revision(run, request.expected_revision)
        story = self._editable_story(run)
        fields = tuple(
            LockedField(json_pointer=pointer, value_sha256=self._field_hash(story, pointer))
            for pointer in request.json_pointers
        )
        if len(set(request.json_pointers)) != len(request.json_pointers):
            raise ServiceError("LOCK_INVALID", "Lock paths must be unique", 422)
        result = updated(
            run, locked_fields=fields, state=updated(run.state, revision=run.state.revision + 1)
        )
        self.database.save(result, run.state.revision, "Story field locks updated", receipt=receipt)
        return result

    _field_hash = staticmethod(story_field_hash)

    @staticmethod
    def _editable_story(run: RunRecord) -> "NarrativeDraft":
        if run.state.node != "narrative_review" or run.state.status not in (
            "waiting_review",
            "needs_changes",
        ):
            raise ServiceError(
                "STORY_NOT_EDITABLE", "Story editing requires the narrative review stage"
            )
        artifact = next(
            (
                item
                for item in reversed(run.artifacts)
                if item.reference.artifact_id == run.state.run_id + ":draft"
            ),
            None,
        )
        if artifact is None:
            raise ServiceError("ARTIFACT_MISSING", "Story draft is missing")
        return NarrativeDraft.model_validate_json(artifact.payload_json)

    def revise(
        self, run_id: str, request: "SubmitRevision", actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.authorize(actor, run.state.project_id, "narrative")
        self.require_revision(run, request.expected_revision)
        previous = self._editable_story(run)
        replacement = request.replacement_story
        if request.facts_changed:
            raise ServiceError(
                "EVIDENCE_REVIEW_REQUIRED",
                "New factual premises need the evidence workflow before revision",
            )
        if (
            replacement.package.project_id != run.state.project_id
            or replacement.package.evidence_package_hash != previous.package.evidence_package_hash
            or replacement.package.routes != previous.package.routes
            or replacement.package.candidate_id != previous.package.candidate_id
        ):
            raise ServiceError(
                "STORY_DEPENDENCY_CHANGED",
                "Revisions must retain the reviewed evidence, route and direction",
            )
        for field in run.locked_fields:
            if self._field_hash(replacement, field.json_pointer) != field.value_sha256:
                raise ServiceError("FIELD_LOCKED", "Revision changes a locked game field")
        version = "edit-" + str(run.state.revision + 1)
        package = updated(replacement.package, content_version=version)
        replacement = updated(replacement, package=package)
        reference = ArtifactRef(
            artifact_id=run.state.run_id + ":narrative",
            project_id=run.state.project_id,
            kind="narrative",
            schema_version="0.1.0",
            content_version=version,
            sha256=CanonicalSerializer.digest(package),
        )
        draft_ref = updated(
            reference,
            artifact_id=run.state.run_id + ":draft",
            kind="report",
            sha256=CanonicalSerializer.digest(replacement),
        )
        review = ReviewRequest(
            request_id=run.state.run_id + ":narrative:" + version,
            gate="narrative",
            targets=(
                ReviewTarget(
                    target_id=reference.artifact_id,
                    version=version,
                    sha256=reference.sha256,
                    gate="narrative",
                ),
            ),
        )
        result = updated(
            run,
            artifacts=(
                *run.artifacts,
                StoredArtifact(reference=reference, payload_json=package.model_dump_json()),
                StoredArtifact(reference=draft_ref, payload_json=replacement.model_dump_json()),
            ),
            review_requests=tuple(item for item in run.review_requests if item.gate != "narrative")
            + (review,),
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                status="waiting_review",
                narrative_ref=reference,
                pending_review_id=review.request_id,
            ),
        )
        self.database.save(
            result,
            run.state.revision,
            "Manual story revision awaiting fresh review",
            receipt=receipt,
        )
        return result

    def revoke_review(
        self, run_id: str, request: RevokeReview, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.run(run_id, actor)
        self.require_revision(run, request.expected_revision)
        decision = next(
            (
                item
                for item in self.database.reviews(run_id)
                if item.decision_id == request.decision_id
            ),
            None,
        )
        if decision is None or request.decision_id in self.database.revoked_reviews(run_id):
            raise ServiceError("REVIEW_STALE", "Review is missing or already revoked")
        role = "publisher" if decision.gate == "publication" else decision.gate
        self.authority.actor(actor.actor_id, run.state.project_id, role)
        revocation = ReviewRevocation(
            decision_id=request.decision_id,
            run_id=run_id,
            actor_id=actor.actor_id,
            reason=request.reason,
            created_at=datetime.now(UTC),
        )
        terminal = run.state.status in ("published", "cancelled", "no_feasible_story")
        result = updated(
            run,
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                status=run.state.status if terminal else "needs_review",
            ),
        )
        self.database.revoke_review(result, run.state.revision, revocation, receipt)
        return result
