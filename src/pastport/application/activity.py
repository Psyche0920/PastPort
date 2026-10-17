"""Meter automatic workflow wall time once, excluding human and queue waiting."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from pastport.application.models import ServiceError
from pastport.application.reliability import OperationReservation, Usage, UsageSettlement
from pastport.ports.editorial import EditorialRepository


class ActivityMeter:
    def __init__(self, database: EditorialRepository) -> None:
        self.database = database
        self.started: float | None = None
        self.allowance = 0

    def elapsed(self) -> int:
        if self.started is None:
            return 0
        return max(1, int((time.monotonic() - self.started) * 1000))

    def remaining(self) -> int:
        return max(0, self.allowance - self.elapsed())

    def check(self) -> None:
        if self.started is not None and self.elapsed() > self.allowance:
            raise ServiceError("BUDGET_EXHAUSTED", "Automatic processing time budget exhausted")

    @contextmanager
    def measure(self, run_id: str, phase: str) -> Iterator[None]:
        if self.started is not None:
            raise RuntimeError("Nested workflow activity measurement is forbidden")
        budget = self.database.budget(run_id)
        for entry in budget.entries:
            if entry.state == "unknown":
                receipt = self.database.execution_receipt(entry.operation_id)
                if receipt is not None and receipt.settlement is not None:
                    self.database.finish_operation(
                        entry.operation_id, receipt.model_dump_json(), 0, receipt.settlement
                    )
        budget = self.database.budget(run_id)
        if any(e.state == "unknown" for e in budget.entries):
            raise ServiceError(
                "OUTCOME_UNKNOWN", "Resolve unknown usage before scheduling new work"
            )
        allowance = (
            budget.limit.active_milliseconds
            - budget.used.active_milliseconds
            - budget.held.active_milliseconds
        )
        if allowance <= 0:
            raise ServiceError("BUDGET_EXHAUSTED", "No processing time remains")
        operation_id = run_id + ":activity:" + phase + ":" + str(uuid4())
        self.database.reserve_operation(
            OperationReservation(
                operation_id=operation_id,
                run_id=run_id,
                input_hash="0" * 64,
                reserved=Usage(active_milliseconds=allowance),
            )
        )
        self.allowance = allowance
        self.started = time.monotonic()
        try:
            try:
                yield
            except BaseException:
                self.database.fail_operation(operation_id, self.elapsed())
                raise
            else:
                elapsed = self.elapsed()
                self.database.finish_operation(
                    operation_id,
                    '"activity_completed"',
                    elapsed,
                    UsageSettlement(actual=Usage(active_milliseconds=elapsed)),
                )
                if elapsed > allowance:
                    raise ServiceError(
                        "BUDGET_EXHAUSTED", "Actual processing time exceeded its allowance"
                    )
        finally:
            self.started = None
            self.allowance = 0
