"""Human interventions preserve spending facts, review history and execution limits."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pastport.application.execution_models import ExecutionBinding, ExecutionReceipt
from pastport.application.models import Actor, RequestReceipt, RunRecord, ServiceError
from pastport.application.operations import (
    AmendBudget,
    BudgetAmendment,
    InterventionSnapshot,
    ReconcileUsage,
    ReconciliationTarget,
    ResubmitReview,
    ReviewResubmission,
    UsageReconciliation,
)
from pastport.application.reliability import ReviewAuthority, ReviewRevocation, Usage
from pastport.application.service import EditorialService
from pastport.application.updates import updated
from pastport.domain.common import CanonicalSerializer
from pastport.domain.packages import ReviewTarget
from pastport.domain.workflow import WorkflowError
from pastport.ports.editorial import EditorialRepository


class OperationalService:
    def __init__(
        self,
        database: EditorialRepository,
        authority: ReviewAuthority,
        targets: Callable[[RunRecord, str], tuple[ReviewTarget, ...]],
    ) -> None:
        self.database = database
        self.authority = authority
        self.targets = targets

    def authorized(self, run_id: str, actor: Actor, role: str) -> RunRecord:
        run = self.database.run(run_id)
        EditorialService.authorize(actor, run.state.project_id, role)
        self.authority.actor(actor.actor_id, run.state.project_id, role)
        return run

    def inspect(self, run_id: str, actor: Actor) -> InterventionSnapshot:
        self.authorized(run_id, actor, "operator")
        policy = self.database.budget_policy(run_id)
        return InterventionSnapshot(
            run_id=run_id,
            budget_policy=policy,
            budget_hash=CanonicalSerializer.digest(policy),
            unknown_entries=tuple(
                ReconciliationTarget(entry=e, entry_hash=CanonicalSerializer.digest(e))
                for e in self.database.budget(run_id).entries
                if e.state == "unknown"
            ),
            history=self.database.interventions(run_id),
        )

    def paused(self, run: RunRecord, revision: int, *, terminal: bool = False) -> None:
        EditorialService.require_revision(run, revision)
        if run.state.status in ("queued", "running") or (
            not terminal and run.state.status in ("published", "cancelled", "no_feasible_story")
        ):
            raise ServiceError(
                "INTERVENTION_NOT_ALLOWED", "This intervention requires a stopped unfinished run"
            )
        if any(e.state == "reserved" for e in self.database.budget(run.state.run_id).entries):
            raise ServiceError("EXECUTION_ACTIVE", "Wait for active execution to stop")

    @staticmethod
    def result(run: RunRecord, *, retry: bool = False) -> RunRecord:
        return updated(
            run,
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                status="blocked" if retry else run.state.status,
                last_error=WorkflowError(
                    code="INTERVENTION_RECORDED",
                    message="Authorized intervention saved; resume explicitly",
                    retryable=True,
                    owner="workflow",
                    field_path="",
                )
                if retry
                else run.state.last_error,
            ),
        )

    def amend(
        self, run_id: str, command: AmendBudget, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.authorized(run_id, actor, "operator")
        self.paused(run, command.expected_revision)
        previous = self.database.budget_policy(run_id)
        if command.budget_hash != CanonicalSerializer.digest(previous):
            raise ServiceError("BUDGET_STALE", "Budget differs from the authorized version")
        if command.budget_policy == previous and not command.accepted_recorded_usage:
            raise ServiceError("BUDGET_UNCHANGED", "New limits must differ from the current limits")
        entries = {entry.operation_id: entry for entry in self.database.budget(run_id).entries}
        accepted_ids = [item.operation_id for item in command.accepted_recorded_usage]
        if len(accepted_ids) != len(set(accepted_ids)):
            raise ServiceError("RECORDED_USAGE_INVALID", "Duplicate recorded usage acceptance")
        for acceptance in command.accepted_recorded_usage:
            entry = entries.get(acceptance.operation_id)
            saved = self.database.execution_receipt(acceptance.operation_id)
            if (
                entry is None or entry.state != "settled" or entry.settlement is None
                or saved is None or saved.response is None or saved.settlement is None
                or saved.settlement != entry.settlement
                or CanonicalSerializer.digest(saved) != acceptance.receipt_sha256
            ):
                raise ServiceError(
                    "RECORDED_USAGE_INVALID", "Acceptance requires the unchanged settled provider receipt"
                )
        result = self.result(run, retry=run.state.status == "budget_exhausted")
        self.database.amend_budget(
            result,
            BudgetAmendment(
                amendment_id=str(uuid4()),
                run_id=run_id,
                actor_id=actor.actor_id,
                created_at=datetime.now(UTC),
                previous_policy=previous,
                command=command,
            ),
            receipt,
        )
        return result

    def reconcile(
        self, run_id: str, command: ReconcileUsage, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.authorized(run_id, actor, "operator")
        self.paused(run, command.expected_revision, terminal=True)
        budget = self.database.budget(run_id)
        entry = next(
            (e for e in budget.entries if e.reservation_id == command.reservation_id), None
        )
        if (
            entry is None
            or entry.state != "unknown"
            or CanonicalSerializer.digest(entry) != command.entry_hash
        ):
            raise ServiceError(
                "RECONCILIATION_STALE", "Choose an unchanged unknown reservation from this run"
            )
        if command.settlement.source != "operator":
            raise ServiceError(
                "RECONCILIATION_SOURCE_INVALID",
                "Manual settlements must identify their operator source",
            )
        actual = command.settlement.actual
        for field in Usage.model_fields:
            if getattr(entry.reserved, field) == 0 and getattr(actual, field) != 0:
                raise ServiceError(
                    "USAGE_SCOPE_INVALID",
                    "Settlement adds usage outside this reservation's dimensions",
                )
        external = any(
            getattr(entry.reserved, key)
            for key in (
                "model_requests",
                "input_tokens",
                "output_tokens",
                "cost_microusd",
                "search_requests",
            )
        ) or bool(
            entry.reserved.fetch_requests and entry.price_reference != "registered-local-source"
        )
        if external and command.evidence.kind != "provider_receipt":
            raise ServiceError(
                "RECONCILIATION_EVIDENCE_REQUIRED",
                "External usage requires a provider receipt attestation",
            )
        original = self.database.execution_receipt(entry.operation_id)
        recovered: ExecutionReceipt | None = None
        if command.action == "retry":
            if actual != Usage() or (
                original is not None
                and (original.response is not None or original.settlement is not None)
            ):
                raise ServiceError(
                    "RETRY_UNSAFE", "Retry requires proof of non-execution and no saved response"
                )
        elif command.action == "recover":
            wire = self.database.provider_request(entry.operation_id)
            if (
                original is None
                or original.response is None
                or original.settlement is not None
                or wire is None
            ):
                raise ServiceError(
                    "RESPONSE_UNAVAILABLE", "Recover requires the original saved model response"
                )
            response = original.response
            if actual.model_requests != 1 or any(
                expected is not None and expected != observed
                for expected, observed in (
                    (response.input_tokens, actual.input_tokens),
                    (response.output_tokens, actual.output_tokens),
                    (response.provider_request_id, command.settlement.provider_request_id),
                )
            ):
                raise ServiceError(
                    "RECEIPT_MISMATCH", "Usage identity differs from the saved response"
                )
            artifact = next(
                (
                    a
                    for a in run.artifacts
                    if a.reference.artifact_id == run_id + ":execution-binding"
                ),
                None,
            )
            if artifact is None:
                raise ServiceError("ARTIFACT_MISSING", "Original execution binding is missing")
            binding = ExecutionBinding.model_validate_json(artifact.payload_json)
            if CanonicalSerializer.digest(binding) != artifact.reference.sha256:
                raise ServiceError("ARTIFACT_CHANGED", "Execution binding failed integrity checks")
            policy = next(
                (
                    m
                    for m in binding.settings.models
                    if entry.price_reference
                    == m.price_version + ":" + CanonicalSerializer.digest(m)
                ),
                None,
            )
            if (
                policy is None
                or policy.model != wire.model
                or policy.cost(actual.input_tokens, actual.output_tokens) != actual.cost_microusd
            ):
                raise ServiceError(
                    "PRICE_MISMATCH", "Settlement differs from the pinned model and price"
                )
            recovered = updated(
                original,
                response=updated(
                    response, input_tokens=actual.input_tokens, output_tokens=actual.output_tokens
                ),
                settlement=command.settlement,
            )
        unresolved = any(
            e.state == "unknown" and e.reservation_id != entry.reservation_id
            for e in budget.entries
        )
        resumable = command.action in ("retry", "recover") or ":activity:" in entry.operation_id
        retry = (
            resumable
            and not unresolved
            and run.state.status == "needs_review"
            and run.state.last_error is not None
            and run.state.last_error.code == "OUTCOME_UNKNOWN"
        )
        result = self.result(run, retry=retry)
        if (
            command.action == "settle"
            and ":activity:" not in entry.operation_id
            and run.state.status not in ("published", "cancelled", "no_feasible_story")
        ):
            result = updated(
                result,
                state=updated(
                    result.state,
                    status="needs_review",
                    last_error=WorkflowError(
                        code="OPERATION_ABANDONED",
                        message=(
                            "Usage resolved without a recoverable result; create a replacement run"
                        ),
                        retryable=False,
                        owner="workflow",
                        field_path="",
                    ),
                ),
            )
        self.database.reconcile_usage(
            result,
            UsageReconciliation(
                reconciliation_id=str(uuid4()),
                run_id=run_id,
                actor_id=actor.actor_id,
                created_at=datetime.now(UTC),
                command=command,
                original_entry=entry,
                original_receipt=original,
                original_receipt_hash=CanonicalSerializer.digest(original)
                if original is not None
                else None,
                recovered_receipt=recovered,
            ),
            receipt,
        )
        return result

    def resubmit(
        self, run_id: str, command: ResubmitReview, actor: Actor, receipt: RequestReceipt
    ) -> RunRecord:
        run = self.database.run(run_id)
        EditorialService.authorize(actor, run.state.project_id)
        self.paused(run, command.expected_revision)
        if run.state.status != "needs_review":
            raise ServiceError(
                "RESUBMISSION_NOT_ALLOWED", "Only a stopped revoked review can be resubmitted"
            )
        decisions = self.database.reviews(run_id)
        revoked = set(self.database.revoked_reviews(run_id))
        selected = next(
            (
                d
                for d in decisions
                if d.decision_id == command.decision_id and d.decision_id in revoked
            ),
            None,
        )
        if selected is None:
            raise ServiceError("REVIEW_STALE", "Select an existing revoked decision")
        gates: tuple[Literal["evidence", "narrative", "publication"], ...] = (
            "evidence",
            "narrative",
            "publication",
        )
        affected = gates[gates.index(selected.gate) :]
        self.authorized(
            run_id, actor, "publisher" if selected.gate == "publication" else selected.gate
        )
        targets = self.targets(run, selected.gate)
        identity = (selected.target_id, selected.target_version, selected.target_hash)
        if identity not in {(t.target_id, t.version, t.sha256) for t in targets}:
            raise ServiceError("REVIEW_STALE", "Revoked decision does not match current targets")
        # Earlier unresolved gates must be handled first; old revoked decisions superseded by
        # a current approval do not permanently block later resubmissions.
        for gate in gates[: gates.index(selected.gate)]:
            for target in self.targets(run, gate):
                latest = next(
                    (
                        d
                        for d in reversed(decisions)
                        if (d.gate, d.target_id, d.target_version, d.target_hash)
                        == (gate, target.target_id, target.version, target.sha256)
                    ),
                    None,
                )
                if latest is None or latest.decision_id in revoked or latest.decision != "approved":
                    raise ServiceError(
                        "EARLIER_REVIEW_REQUIRED", "Resubmit the earliest invalid review first"
                    )
                self.authority.decision(latest, run.state.project_id)
        latest_selected = next(
            (
                d
                for d in reversed(decisions)
                if (d.gate, d.target_id, d.target_version, d.target_hash)
                == (selected.gate, *identity)
            ),
            None,
        )
        if latest_selected != selected:
            raise ServiceError("REVIEW_STALE", "A later decision supersedes this revocation")
        now = datetime.now(UTC)
        cascade = tuple(
            ReviewRevocation(
                decision_id=d.decision_id,
                run_id=run_id,
                actor_id=actor.actor_id,
                reason="Dependency invalidated by resubmission: " + command.reason,
                created_at=now,
                kind="dependency",
            )
            for d in decisions
            if d.gate in affected and d.decision == "approved" and d.decision_id not in revoked
        )
        node = (
            "evidence_review"
            if selected.gate == "evidence"
            else "narrative_review"
            if selected.gate == "narrative"
            else "publish_review"
        )
        result = updated(
            run,
            control=updated(run.control, release_generation=run.control.release_generation + 1),
            review_requests=tuple(r for r in run.review_requests if r.gate not in affected),
            state=updated(
                run.state,
                revision=run.state.revision + 1,
                node=node,
                status="running",
                pending_review_id=None,
                pending_request_id=None,
                last_error=None,
                approved_route_ref=None
                if selected.gate == "evidence"
                else run.state.approved_route_ref,
            ),
        )
        self.database.resubmit_review(
            result,
            ReviewResubmission(
                resubmission_id=str(uuid4()),
                run_id=run_id,
                actor_id=actor.actor_id,
                created_at=now,
                command=command,
                gate=selected.gate,
                revoked_decision_ids=tuple(d.decision_id for d in cascade),
            ),
            cascade,
            receipt,
        )
        return result
