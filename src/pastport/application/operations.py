"""Authenticated intervention commands and immutable audit records."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from pastport.application.execution_models import ExecutionReceipt
from pastport.application.reliability import LedgerEntry, UsageSettlement
from pastport.domain.common import Contract, Identifier, NonNegative, Sha256, Text
from pastport.domain.workflow import BudgetPolicy


class ReconciliationEvidence(Contract):
    kind: Literal["provider_receipt", "local_execution_record"]
    reference: Text
    description: Annotated[str, Field(min_length=1, max_length=65536)]


class ReconcileUsage(Contract):
    expected_revision: NonNegative
    reservation_id: Identifier
    entry_hash: Sha256
    action: Literal["recover", "retry", "settle"]
    settlement: UsageSettlement
    evidence: ReconciliationEvidence
    reason: Text


class UsageReconciliation(Contract):
    reconciliation_id: Identifier
    run_id: Identifier
    actor_id: Identifier
    created_at: AwareDatetime
    command: ReconcileUsage
    original_entry: LedgerEntry
    original_receipt_hash: Sha256 | None
    recovered_receipt: ExecutionReceipt | None


class AmendBudget(Contract):
    expected_revision: NonNegative
    budget_hash: Sha256
    budget_policy: BudgetPolicy
    reason: Text


class BudgetAmendment(Contract):
    amendment_id: Identifier
    run_id: Identifier
    actor_id: Identifier
    created_at: AwareDatetime
    previous_policy: BudgetPolicy
    command: AmendBudget


class ResubmitReview(Contract):
    expected_revision: NonNegative
    decision_id: Identifier
    reason: Text


class ReviewResubmission(Contract):
    resubmission_id: Identifier
    run_id: Identifier
    actor_id: Identifier
    created_at: AwareDatetime
    command: ResubmitReview
    gate: Literal["evidence", "narrative", "publication"]
    revoked_decision_ids: tuple[Identifier, ...]


class InterventionHistory(Contract):
    reconciliations: tuple[UsageReconciliation, ...]
    budget_amendments: tuple[BudgetAmendment, ...]
    review_resubmissions: tuple[ReviewResubmission, ...]


class ReconciliationTarget(Contract):
    entry: LedgerEntry
    entry_hash: Sha256


class InterventionSnapshot(Contract):
    run_id: Identifier
    budget_policy: BudgetPolicy
    budget_hash: Sha256
    unknown_entries: tuple[ReconciliationTarget, ...]
    history: InterventionHistory
