"""Short SQLite transactions with optimistic revisions and durable command consumption."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pastport.application.execution_models import (
    ExecutionGrant,
    ExecutionReceipt,
    ExecutionSummary,
    ProviderRequest,
)
from pastport.application.models import (
    ProjectRecord,
    RequestReceipt,
    RunEvent,
    RunRecord,
    ServiceError,
    StoredArtifact,
    StoredCommand,
)
from pastport.application.operations import (
    BudgetAmendment,
    InterventionHistory,
    ReviewResubmission,
    UsageReconciliation,
)
from pastport.application.reliability import (
    BudgetSnapshot,
    LedgerEntry,
    OperationReservation,
    ReleaseRecord,
    ReviewRevocation,
    Usage,
    UsageSettlement,
)
from pastport.application.updates import updated
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract, ReviewDecision
from pastport.domain.packages import ReviewSnapshot
from pastport.domain.workflow import BudgetPolicy

MIGRATION = """
CREATE TABLE IF NOT EXISTS usage_reconciliations(
 identity TEXT PRIMARY KEY,run_id TEXT NOT NULL,payload_json TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget_amendments(
 identity TEXT PRIMARY KEY,run_id TEXT NOT NULL,payload_json TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_resubmissions(
 identity TEXT PRIMARY KEY,run_id TEXT NOT NULL,payload_json TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS provider_requests(
 operation_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS execution_grants(
 reservation_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS execution_receipts(
 operation_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,
 payload_json TEXT NOT NULL,sha256 TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS projects(
 project_id TEXT PRIMARY KEY, provider TEXT NOT NULL, folder_id TEXT NOT NULL,
 payload_json TEXT NOT NULL, UNIQUE(provider, folder_id));
CREATE TABLE IF NOT EXISTS workflow_runs(
 run_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
 revision INTEGER NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_writable_run ON workflow_runs(project_id)
 WHERE status NOT IN ('published','cancelled','no_feasible_story');
CREATE TABLE IF NOT EXISTS commands(
 command_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 state TEXT NOT NULL CHECK(state IN ('pending','running','applied')));
CREATE TABLE IF NOT EXISTS run_events(
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 revision INTEGER NOT NULL, node TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(
 project_id TEXT NOT NULL, artifact_id TEXT NOT NULL, content_version TEXT NOT NULL,
 sha256 TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(project_id,artifact_id,content_version));
CREATE TABLE IF NOT EXISTS review_decisions(
 decision_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 target_id TEXT NOT NULL, target_hash TEXT NOT NULL, actor_id TEXT NOT NULL,
 payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_requests(
 request_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_settings(environment TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS execution_units(
 operation_id TEXT PRIMARY KEY, state TEXT NOT NULL, result_json TEXT,
 active_milliseconds INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS budget_accounts(
 run_id TEXT PRIMARY KEY REFERENCES workflow_runs(run_id), policy_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage_ledger(
 reservation_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 state TEXT NOT NULL CHECK(state IN ('reserved','settled','unknown')), payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_revocations(
 decision_id TEXT PRIMARY KEY REFERENCES review_decisions(decision_id),
 run_id TEXT NOT NULL REFERENCES workflow_runs(run_id), payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releases(
 release_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
 run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 status TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_releases(
 project_id TEXT PRIMARY KEY REFERENCES projects(project_id),
 release_id TEXT NOT NULL REFERENCES releases(release_id));
CREATE TABLE IF NOT EXISTS idempotency(
 scope TEXT NOT NULL, request_key TEXT NOT NULL, payload_hash TEXT NOT NULL,
 response_json TEXT NOT NULL, status_code INTEGER NOT NULL, PRIMARY KEY(scope,request_key));
"""


class EditorialDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as error:
            raise ServiceError(
                "DATABASE_UNAVAILABLE", "Editorial database is unavailable", 503
            ) from error
        try:
            yield connection
        except sqlite3.Error as error:
            connection.rollback()
            raise ServiceError(
                "DATABASE_ERROR", "Editorial database operation failed", 503
            ) from error
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if tables and "schema_versions" not in tables:
                raise ServiceError(
                    "DATABASE_SCHEMA_UNKNOWN", "Refusing to alter an unrelated database", 503
                )
            if "schema_versions" in tables:
                version = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[
                    0
                ]
                if version is not None and version not in (1, 2, 3, 4):
                    raise ServiceError(
                        "DATABASE_VERSION_UNSUPPORTED", "Database needs an explicit migration", 503
                    )
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("BEGIN IMMEDIATE;\n" + MIGRATION)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(execution_units)")}
            for name, definition in (
                ("input_hash", "TEXT"),
                ("result_sha256", "TEXT"),
                ("attempts", "INTEGER NOT NULL DEFAULT 0"),
                ("reservation_id", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE execution_units ADD COLUMN {name} {definition}"
                    )
            self._migrate_budgets(connection)
            connection.execute("DELETE FROM schema_versions")
            connection.execute("INSERT INTO schema_versions VALUES(4)")
            connection.commit()

    def create_project(self, project: ProjectRecord, receipt: RequestReceipt) -> ProjectRecord:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM projects WHERE provider=? AND folder_id=?",
                (project.provider, project.folder_id),
            ).fetchone()
            if row:
                existing_project = ProjectRecord.model_validate_json(row[0])
                if existing_project.project_id != project.project_id:
                    raise ServiceError(
                        "SOURCE_ALREADY_REGISTERED", "This source folder is already registered"
                    )
                self._receipt(connection, receipt, existing_project.model_dump_json())
                connection.commit()
                return existing_project
            connection.execute(
                "INSERT INTO projects VALUES(?,?,?,?)",
                (
                    project.project_id,
                    project.provider,
                    project.folder_id,
                    project.model_dump_json(),
                ),
            )
            self._receipt(connection, receipt, project.model_dump_json())
            connection.commit()
        return project

    def project(self, project_id: str) -> ProjectRecord:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
        if row is None:
            raise ServiceError("PROJECT_NOT_FOUND", "Project does not exist", 404)
        return ProjectRecord.model_validate_json(row[0])

    def projects(self) -> tuple[ProjectRecord, ...]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM projects ORDER BY project_id"
            ).fetchall()
        return tuple(ProjectRecord.model_validate_json(row[0]) for row in rows)

    def create_run(self, run: RunRecord, receipt: RequestReceipt) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                (
                    "SELECT run_id FROM workflow_runs WHERE project_id=? AND status "
                    "NOT IN ('published','cancelled','no_feasible_story')"
                ),
                (run.state.project_id,),
            ).fetchone()
            if existing:
                raise ServiceError("PROJECT_BUSY", "Project already has an active run")
            connection.execute(
                "INSERT INTO workflow_runs VALUES(?,?,?,?,?)",
                (
                    run.state.run_id,
                    run.state.project_id,
                    run.state.revision,
                    run.state.status,
                    run.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO budget_accounts VALUES(?,?)",
                (run.state.run_id, run.budget_policy.model_dump_json()),
            )
            self._enqueue(connection, run.state.run_id)
            self._event(connection, run, "Run created")
            self._receipt(connection, receipt, run.model_dump_json())
            connection.commit()

    def run(self, run_id: str) -> RunRecord:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workflow_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise ServiceError("RUN_NOT_FOUND", "Run does not exist", 404)
        return RunRecord.model_validate_json(row[0])

    def save(
        self,
        run: RunRecord,
        previous_revision: int,
        message: str,
        *,
        enqueue: bool = False,
        receipt: RequestReceipt | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._save_record(connection, run, previous_revision, message, enqueue, receipt)
            connection.commit()

    def save_review(
        self, run: RunRecord, previous_revision: int, receipt: RequestReceipt, *, enqueue: bool
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._save_record(
                connection,
                run,
                previous_revision,
                "Review decisions saved",
                enqueue,
                receipt,
                allow_review_write=True,
            )
            connection.commit()

    def _save_record(
        self,
        connection: sqlite3.Connection,
        run: RunRecord,
        previous_revision: int,
        message: str,
        enqueue: bool = False,
        receipt: RequestReceipt | None = None,
        *,
        allow_review_write: bool = False,
    ) -> None:
        if run.state.revision != previous_revision + 1:
            raise ServiceError(
                "REVISION_INVALID", "A mutation must increment revision exactly once"
            )
        changed = connection.execute(
            (
                "UPDATE workflow_runs SET revision=?,status=?,payload_json=? "
                "WHERE run_id=? AND revision=?"
            ),
            (
                run.state.revision,
                run.state.status,
                run.model_dump_json(),
                run.state.run_id,
                previous_revision,
            ),
        )
        if changed.rowcount != 1:
            raise ServiceError("STATE_STALE", "Run changed; reload before retrying")
        authoritative = self._reviews(connection, run.state.run_id)
        if allow_review_write and run.review_decisions[: len(authoritative)] != authoritative:
            raise ServiceError("REVIEW_IMMUTABLE", "Review history cannot be removed or changed")
        if not allow_review_write and run.review_decisions != authoritative:
            raise ServiceError(
                "APPROVAL_WRITE_FORBIDDEN", "Only the review use case can append decisions"
            )
        for artifact in run.artifacts:
            reference = artifact.reference
            old = connection.execute(
                (
                    "SELECT sha256 FROM artifacts WHERE project_id=? AND "
                    "artifact_id=? AND content_version=?"
                ),
                (
                    reference.project_id,
                    reference.artifact_id,
                    reference.content_version,
                ),
            ).fetchone()
            if old and old[0] != reference.sha256:
                raise ServiceError(
                    "ARTIFACT_IMMUTABLE", "An existing content version cannot be overwritten"
                )
            connection.execute(
                "INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?)",
                (
                    reference.project_id,
                    reference.artifact_id,
                    reference.content_version,
                    reference.sha256,
                    artifact.payload_json,
                ),
            )
        for request in run.review_requests:
            stored = connection.execute(
                "SELECT payload_json FROM review_requests WHERE request_id=?", (request.request_id,)
            ).fetchone()
            if stored and stored[0] != request.model_dump_json():
                raise ServiceError("REVIEW_IMMUTABLE", "Review requests are immutable")
            connection.execute(
                "INSERT OR IGNORE INTO review_requests VALUES(?,?,?)",
                (request.request_id, run.state.run_id, request.model_dump_json()),
            )
        for decision in run.review_decisions:
            old = connection.execute(
                "SELECT payload_json FROM review_decisions WHERE decision_id=?",
                (decision.decision_id,),
            ).fetchone()
            if old and old[0] != decision.model_dump_json():
                raise ServiceError("REVIEW_IMMUTABLE", "Review decisions are append-only")
            connection.execute(
                "INSERT OR IGNORE INTO review_decisions VALUES(?,?,?,?,?,?)",
                (
                    decision.decision_id,
                    run.state.run_id,
                    decision.target_id,
                    decision.target_hash,
                    decision.actor_id,
                    decision.model_dump_json(),
                ),
            )
        if enqueue:
            self._enqueue(connection, run.state.run_id)
        self._event(connection, run, message)
        if receipt is not None:
            self._receipt(connection, receipt, run.model_dump_json())

    @staticmethod
    def _enqueue(connection: sqlite3.Connection, run_id: str) -> None:
        connection.execute("INSERT INTO commands VALUES(?,?,'pending')", (str(uuid4()), run_id))

    @staticmethod
    def _event(connection: sqlite3.Connection, run: RunRecord, message: str) -> None:
        connection.execute(
            "INSERT INTO run_events(run_id,revision,node,status,message) VALUES(?,?,?,?,?)",
            (
                run.state.run_id,
                run.state.revision,
                run.state.node,
                run.state.status,
                message,
            ),
        )

    def recover_commands(self) -> None:
        with self.connection() as connection:
            connection.execute("UPDATE commands SET state='pending' WHERE state='running'")
            connection.execute(
                "UPDATE execution_units SET state='unknown_outcome' WHERE state='running'"
            )
            for row in connection.execute(
                "SELECT payload_json FROM usage_ledger WHERE state='reserved'"
            ).fetchall():
                entry = updated(LedgerEntry.model_validate_json(row[0]), state="unknown")
                connection.execute(
                    "UPDATE usage_ledger SET state='unknown',payload_json=? WHERE reservation_id=?",
                    (entry.model_dump_json(), entry.reservation_id),
                )
            connection.commit()

    def claim_command(self) -> StoredCommand | None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT command_id,run_id FROM commands WHERE state='pending' "
                "ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute("UPDATE commands SET state='running' WHERE command_id=?", (row[0],))
            connection.commit()
        return StoredCommand(command_id=row[0], run_id=row[1])

    def finish_command(self, command_id: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE commands SET state='applied' WHERE command_id=?", (command_id,)
            )
            connection.commit()

    def events(self, run_id: str, after: int) -> tuple[RunEvent, ...]:
        with self.connection() as connection:
            rows = connection.execute(
                (
                    "SELECT * FROM run_events WHERE run_id=? AND event_id>? ORDER BY "
                    "event_id LIMIT 200"
                ),
                (run_id, after),
            ).fetchall()
        return tuple(
            RunEvent(
                event_id=row["event_id"],
                run_id=row["run_id"],
                revision=row["revision"],
                node=row["node"],
                status=row["status"],
                message=row["message"],
            )
            for row in rows
        )

    @staticmethod
    def _receipt(
        connection: sqlite3.Connection, receipt: RequestReceipt, response_json: str
    ) -> None:
        connection.execute(
            "INSERT INTO idempotency VALUES(?,?,?,?,?)",
            (
                receipt.scope,
                receipt.request_key,
                receipt.payload_hash,
                response_json,
                receipt.status_code,
            ),
        )

    def receipt(self, scope: str, request_key: str, payload_hash: str) -> RequestReceipt | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM idempotency WHERE scope=? AND request_key=?", (scope, request_key)
            ).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            raise ServiceError(
                "IDEMPOTENCY_CONFLICT", "This key was already used with another request"
            )
        return RequestReceipt(
            scope=scope,
            request_key=request_key,
            payload_hash=payload_hash,
            response_json=row["response_json"],
            status_code=row["status_code"],
        )

    def operation_result(self, operation_id: str, input_hash: str | None = None) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM execution_units WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row and row["state"] == "succeeded" and row["reservation_id"]:
                entry = self._ledger_entry(connection, row["reservation_id"])
                if entry.state != "settled" or entry.settlement is None:
                    raise ServiceError(
                        "LEDGER_INCONSISTENT", "Successful execution has no settled usage receipt"
                    )
        if row and input_hash is not None and row["input_hash"] != input_hash:
            raise ServiceError(
                "EXECUTION_INPUT_CHANGED", "Stored execution belongs to different dependencies"
            )
        if row and row["state"] == "abandoned":
            raise ServiceError(
                "OPERATION_ABANDONED",
                "Usage was settled without a recoverable result; create a replacement run",
            )
        if row and row["state"] == "unknown_outcome":
            raise ServiceError(
                "OUTCOME_UNKNOWN", "Interrupted operation needs reconciliation before retry"
            )
        if row and row["state"] == "succeeded":
            result = str(row["result_json"])
            if row["result_sha256"] != hashlib.sha256(result.encode()).hexdigest():
                raise ServiceError(
                    "EXECUTION_RESULT_CHANGED", "Persisted result failed its content hash"
                )
            return result
        return None

    def finish_operation(
        self,
        operation_id: str,
        result_json: str,
        active_milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        actual = settlement or UsageSettlement(
            actual=Usage(active_milliseconds=active_milliseconds)
        )
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM execution_units WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise ServiceError("EXECUTION_MISSING", "Execution was not reserved")
            if row["state"] == "succeeded":
                if row["result_json"] != result_json:
                    raise ServiceError("EXECUTION_IMMUTABLE", "A completed execution cannot change")
                if row["reservation_id"]:
                    entry = self._ledger_entry(connection, row["reservation_id"])
                    if entry.settlement != actual:
                        raise ServiceError(
                            "USAGE_IMMUTABLE", "A settled usage receipt cannot change"
                        )
                return
            settle_required = True
            if row["state"] != "running":
                stored = connection.execute(
                    "SELECT payload_json,sha256 FROM execution_receipts WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                recorded = ExecutionReceipt.model_validate_json(stored[0]) if stored else None
                if (
                    row["state"] not in ("unknown_outcome", "failed")
                    or recorded is None
                    or CanonicalSerializer.digest(recorded) != stored[1]
                    or recorded.model_dump_json() != result_json
                    or recorded.settlement != actual
                ):
                    raise ServiceError(
                        "OUTCOME_UNKNOWN", "Execution requires reconciliation before settlement"
                    )
                entry = self._ledger_entry(connection, row["reservation_id"])
                if entry.state == "unknown":
                    restored = updated(entry, state="reserved")
                    connection.execute(
                        (
                            "UPDATE usage_ledger SET state='reserved',payload_json=? "
                            "WHERE reservation_id=?"
                        ),
                        (restored.model_dump_json(), entry.reservation_id),
                    )
                elif entry.state == "settled" and entry.settlement == actual:
                    settle_required = False
                else:
                    raise ServiceError(
                        "LEDGER_INCONSISTENT", "Receipt does not match unsettled usage"
                    )
            if settle_required:
                self._settle(connection, row["reservation_id"], actual)
            connection.execute(
                "UPDATE execution_units SET state='succeeded',result_json=?,result_sha256=?,"
                "active_milliseconds=active_milliseconds+? WHERE operation_id=?",
                (
                    result_json,
                    hashlib.sha256(result_json.encode()).hexdigest(),
                    actual.actual.active_milliseconds,
                    operation_id,
                ),
            )
            connection.commit()

    def active_milliseconds(self, run_id: str) -> int:
        with self.connection() as connection:
            row = connection.execute(
                (
                    "SELECT COALESCE(SUM(active_milliseconds),0) FROM execution_units "
                    "WHERE operation_id LIKE ?"
                ),
                (run_id + ":%",),
            ).fetchone()
        return int(row[0])

    def bind_environment(self, environment: str) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT environment FROM instance_settings LIMIT 1").fetchone()
            if row and row[0] != environment:
                raise ServiceError(
                    "ENVIRONMENT_MISMATCH",
                    "Use separate data directories for test and production",
                    503,
                )
            if row is None:
                connection.execute("INSERT INTO instance_settings VALUES(?)", (environment,))
            connection.commit()

    def fail_operation(self, operation_id: str, active_milliseconds: int) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM execution_units WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None or row["state"] != "running":
                return
            if row["reservation_id"]:
                entry = self._ledger_entry(connection, row["reservation_id"])
                paid = (
                    entry.reserved.model_requests
                    or entry.reserved.cost_microusd
                    or entry.reserved.input_tokens
                    or entry.reserved.output_tokens
                    or entry.reserved.search_requests
                    or entry.reserved.fetch_requests
                )
                if paid:
                    unknown = updated(entry, state="unknown")
                    connection.execute(
                        (
                            "UPDATE usage_ledger SET state='unknown',payload_json=? WHERE rese"
                            "rvation_id=?"
                        ),
                        (unknown.model_dump_json(), unknown.reservation_id),
                    )
                    connection.execute(
                        "UPDATE execution_units SET state='unknown_outcome' WHERE operation_id=?",
                        (operation_id,),
                    )
                    connection.commit()
                    return
            self._settle(
                connection,
                row["reservation_id"],
                UsageSettlement(actual=Usage(active_milliseconds=active_milliseconds)),
            )
            connection.execute(
                (
                    "UPDATE execution_units SET state='failed',active_milliseconds=act"
                    "ive_milliseconds+? WHERE operation_id=?"
                ),
                (active_milliseconds, operation_id),
            )
            connection.commit()

    @staticmethod
    def _ledger_entry(connection: sqlite3.Connection, reservation_id: str) -> LedgerEntry:
        row = connection.execute(
            "SELECT payload_json FROM usage_ledger WHERE reservation_id=?", (reservation_id,)
        ).fetchone()
        if row is None:
            raise ServiceError("LEDGER_MISSING", "Execution reservation is missing")
        return LedgerEntry.model_validate_json(row[0])

    @staticmethod
    def _settle(
        connection: sqlite3.Connection, reservation_id: str | None, settlement: UsageSettlement
    ) -> None:
        if reservation_id is None:
            return
        entry = EditorialDatabase._ledger_entry(connection, reservation_id)
        if entry.state != "reserved":
            raise ServiceError("USAGE_IMMUTABLE", "Only an active reservation can be settled")
        entry = updated(entry, state="settled", settlement=settlement)
        connection.execute(
            "UPDATE usage_ledger SET state='settled',payload_json=? WHERE reservation_id=?",
            (entry.model_dump_json(), reservation_id),
        )

    @staticmethod
    def _migrate_budgets(connection: sqlite3.Connection) -> None:
        for row in connection.execute("SELECT payload_json FROM workflow_runs").fetchall():
            run = RunRecord.model_validate_json(row[0])
            exists = connection.execute(
                "SELECT 1 FROM budget_accounts WHERE run_id=?", (run.state.run_id,)
            ).fetchone()
            if exists:
                continue
            connection.execute(
                "INSERT INTO budget_accounts VALUES(?,?)",
                (run.state.run_id, run.budget_policy.model_dump_json()),
            )
            operations = connection.execute(
                "SELECT * FROM execution_units WHERE operation_id LIKE ?",
                (run.state.run_id + ":%",),
            ).fetchall()
            milliseconds = sum(int(item["active_milliseconds"]) for item in operations)
            if milliseconds:
                entry = LedgerEntry(
                    reservation_id=run.state.run_id + ":migration",
                    operation_id=run.state.run_id + ":migration",
                    run_id=run.state.run_id,
                    state="settled",
                    reserved=Usage(active_milliseconds=milliseconds),
                    settlement=UsageSettlement(actual=Usage(active_milliseconds=milliseconds)),
                    price_reference=None,
                )
                connection.execute(
                    "INSERT INTO usage_ledger VALUES(?,?,?,?,?)",
                    (
                        entry.reservation_id,
                        entry.operation_id,
                        entry.run_id,
                        entry.state,
                        entry.model_dump_json(),
                    ),
                )
            for operation in operations:
                if operation["state"] in ("running", "unknown_outcome"):
                    entry = LedgerEntry(
                        reservation_id=operation["operation_id"] + ":legacy-unknown",
                        operation_id=operation["operation_id"],
                        run_id=run.state.run_id,
                        state="unknown",
                        reserved=Usage.limits(run.budget_policy),
                        settlement=None,
                        price_reference=None,
                    )
                    connection.execute(
                        "INSERT INTO usage_ledger VALUES(?,?,?,?,?)",
                        (
                            entry.reservation_id,
                            entry.operation_id,
                            entry.run_id,
                            entry.state,
                            entry.model_dump_json(),
                        ),
                    )
        for row in connection.execute(
            "SELECT operation_id,result_json FROM execution_units WHERE state="
            "'succeeded' AND result_sha256 IS NULL"
        ).fetchall():
            connection.execute(
                "UPDATE execution_units SET result_sha256=? WHERE operation_id=?",
                (hashlib.sha256(row[1].encode()).hexdigest(), row[0]),
            )

    def _budget(self, connection: sqlite3.Connection, run_id: str) -> BudgetSnapshot:
        policy = self._budget_policy(connection, run_id)
        rows = connection.execute(
            "SELECT payload_json FROM usage_ledger WHERE run_id=? ORDER BY rowid", (run_id,)
        ).fetchall()
        entries = tuple(LedgerEntry.model_validate_json(item[0]) for item in rows)
        used, held = Usage(), Usage()
        for entry in entries:
            if entry.state == "settled" and entry.settlement is not None:
                used = used.plus(entry.settlement.actual)
            else:
                held = held.plus(entry.reserved)
        maximum = Usage.limits(policy)
        return BudgetSnapshot(
            run_id=run_id,
            limit=maximum,
            used=used,
            held=held,
            entries=entries,
            over_limit=not used.plus(held).fits(maximum),
        )

    def save_grant(self, grant: ExecutionGrant) -> None:
        metadata = grant.metadata
        payload = grant.model_dump_json()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT payload_json FROM execution_grants WHERE reservation_id=?",
                (metadata.budget_reservation_id,),
            ).fetchone()
            if previous and previous[0] != payload:
                raise ServiceError("EXECUTION_GRANT_CHANGED", "An execution grant is immutable")
            connection.execute(
                "INSERT OR IGNORE INTO execution_grants VALUES(?,?,?)",
                (metadata.budget_reservation_id, payload, CanonicalSerializer.digest(grant)),
            )
            connection.commit()

    def execution_grant(self, reservation_id: str) -> ExecutionGrant:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json,sha256 FROM execution_grants WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone()
        if row is None:
            raise ServiceError("EXECUTION_NOT_AUTHORIZED", "No server execution grant exists")
        grant = ExecutionGrant.model_validate_json(row[0])
        if CanonicalSerializer.digest(grant) != row[1]:
            raise ServiceError(
                "EXECUTION_GRANT_CHANGED", "The execution grant failed integrity checks"
            )
        return grant

    def save_provider_request(self, operation_id: str, request: ProviderRequest) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            reserved = connection.execute(
                "SELECT state FROM execution_units WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if reserved is None or reserved[0] != "running":
                raise ServiceError(
                    "EXECUTION_NOT_AUTHORIZED", "Provider request has no active reservation"
                )
            row = connection.execute(
                "SELECT payload_json FROM provider_requests WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row and row[0] != request.model_dump_json():
                raise ServiceError("EXECUTION_INPUT_CHANGED", "The provider request is immutable")
            connection.execute(
                "INSERT OR IGNORE INTO provider_requests VALUES(?,?,?)",
                (operation_id, request.model_dump_json(), CanonicalSerializer.digest(request)),
            )
            connection.commit()

    def provider_request(self, operation_id: str) -> ProviderRequest | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json,sha256 FROM provider_requests WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        request = ProviderRequest.model_validate_json(row[0])
        if CanonicalSerializer.digest(request) != row[1]:
            raise ServiceError(
                "EXECUTION_INPUT_CHANGED", "Provider request failed integrity checks"
            )
        return request

    def save_execution_receipt(
        self, operation_id: str, run_id: str, receipt: ExecutionReceipt
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            unit = connection.execute(
                "SELECT state FROM execution_units WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if unit is None or not operation_id.startswith(run_id + ":"):
                raise ServiceError(
                    "EXECUTION_SCOPE_INVALID", "Receipt has no matching reserved operation"
                )
            old = connection.execute(
                "SELECT payload_json FROM execution_receipts WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if old and old[0] != receipt.model_dump_json():
                raise ServiceError("EXECUTION_IMMUTABLE", "An execution receipt cannot change")
            connection.execute(
                "INSERT OR IGNORE INTO execution_receipts VALUES(?,?,?,?)",
                (
                    operation_id,
                    run_id,
                    receipt.model_dump_json(),
                    CanonicalSerializer.digest(receipt),
                ),
            )
            connection.commit()

    def execution_receipt(self, operation_id: str) -> ExecutionReceipt | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json,sha256 FROM execution_receipts WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        receipt = ExecutionReceipt.model_validate_json(row[0])
        if CanonicalSerializer.digest(receipt) != row[1]:
            raise ServiceError(
                "EXECUTION_RESULT_CHANGED", "Execution receipt failed integrity checks"
            )
        with self.connection() as connection:
            run_id = operation_id.partition(":")[0]
            for resolution in self._audit_records(
                connection, "usage_reconciliations", run_id, UsageReconciliation
            ):
                if (
                    resolution.original_entry.operation_id == operation_id
                    and resolution.recovered_receipt is not None
                ):
                    if resolution.original_receipt_hash != CanonicalSerializer.digest(receipt):
                        raise ServiceError(
                            "EXECUTION_RESULT_CHANGED",
                            "Original receipt differs from reconciliation evidence",
                        )
                    return resolution.recovered_receipt
        return receipt

    def execution_summaries(self, run_id: str) -> tuple[ExecutionSummary, ...]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT operation_id FROM execution_receipts WHERE run_id=? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        result = []
        for row in rows:
            receipt = self.execution_receipt(row[0])
            assert receipt is not None
            result.append(
                ExecutionSummary(
                    operation_id=row[0],
                    receipt_hash=CanonicalSerializer.digest(receipt),
                    artifact_ref=receipt.artifact.reference
                    if receipt.artifact is not None
                    else None,
                    settlement=receipt.settlement,
                    error_code=receipt.error_code,
                )
            )
        return tuple(result)

    def execution_artifact(self, run_id: str, reference: ArtifactRef) -> StoredArtifact | None:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT operation_id FROM execution_receipts WHERE run_id=?", (run_id,)
            ).fetchall()
        for row in rows:
            receipt = self.execution_receipt(row[0])
            if (
                receipt is not None
                and receipt.artifact is not None
                and receipt.artifact.reference == reference
            ):
                return receipt.artifact
        return None

    @staticmethod
    def _audit_records[Record: Contract](
        connection: sqlite3.Connection, table: str, run_id: str, model: type[Record]
    ) -> tuple[Record, ...]:
        records = []
        for row in connection.execute(
            f"SELECT payload_json,sha256 FROM {table} WHERE run_id=? ORDER BY rowid", (run_id,)
        ).fetchall():
            record = model.model_validate_json(row[0])
            if CanonicalSerializer.digest(record) != row[1]:
                raise ServiceError("AUDIT_CHANGED", "Intervention history failed integrity checks")
            records.append(record)
        return tuple(records)

    @staticmethod
    def _append_audit(
        connection: sqlite3.Connection, table: str, identity: str, run_id: str, record: Contract
    ) -> None:
        connection.execute(
            f"INSERT INTO {table} VALUES(?,?,?,?)",
            (identity, run_id, record.model_dump_json(), CanonicalSerializer.digest(record)),
        )

    def interventions(self, run_id: str) -> InterventionHistory:
        with self.connection() as connection:
            return InterventionHistory(
                reconciliations=self._audit_records(
                    connection, "usage_reconciliations", run_id, UsageReconciliation
                ),
                budget_amendments=self._audit_records(
                    connection, "budget_amendments", run_id, BudgetAmendment
                ),
                review_resubmissions=self._audit_records(
                    connection, "review_resubmissions", run_id, ReviewResubmission
                ),
            )

    def _budget_policy(self, connection: sqlite3.Connection, run_id: str) -> BudgetPolicy:
        row = connection.execute(
            "SELECT payload_json FROM workflow_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise ServiceError("RUN_NOT_FOUND", "Run does not exist", 404)
        policy = RunRecord.model_validate_json(row[0]).budget_policy
        for amendment in self._audit_records(
            connection, "budget_amendments", run_id, BudgetAmendment
        ):
            if (
                amendment.previous_policy != policy
                or amendment.command.budget_hash != CanonicalSerializer.digest(policy)
            ):
                raise ServiceError(
                    "BUDGET_POLICY_CHANGED", "Budget amendment chain is inconsistent"
                )
            policy = amendment.command.budget_policy
        account = connection.execute(
            "SELECT policy_json FROM budget_accounts WHERE run_id=?", (run_id,)
        ).fetchone()
        if account is None or account[0] != policy.model_dump_json():
            raise ServiceError(
                "BUDGET_POLICY_CHANGED", "Persisted budget requires an explicit amendment"
            )
        return policy

    def budget_policy(self, run_id: str) -> BudgetPolicy:
        with self.connection() as connection:
            return self._budget_policy(connection, run_id)

    def amend_budget(
        self, run: RunRecord, amendment: BudgetAmendment, receipt: RequestReceipt
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = self._budget_policy(connection, run.state.run_id)
            snapshot = self._budget(connection, run.state.run_id)
            if previous != amendment.previous_policy:
                raise ServiceError("BUDGET_STALE", "Budget changed since authorization")
            if any(e.state == "reserved" for e in snapshot.entries):
                raise ServiceError("EXECUTION_ACTIVE", "Wait for active operations to stop")
            if not snapshot.used.plus(snapshot.held).fits(
                Usage.limits(amendment.command.budget_policy)
            ):
                raise ServiceError(
                    "BUDGET_BELOW_USAGE", "Limits cannot discard spent or held usage"
                )
            self._save_record(
                connection,
                run,
                amendment.command.expected_revision,
                "Budget amended",
                receipt=receipt,
            )
            self._append_audit(
                connection, "budget_amendments", amendment.amendment_id, run.state.run_id, amendment
            )
            connection.execute(
                "UPDATE budget_accounts SET policy_json=? WHERE run_id=?",
                (amendment.command.budget_policy.model_dump_json(), run.state.run_id),
            )
            connection.commit()

    def reconcile_usage(
        self, run: RunRecord, reconciliation: UsageReconciliation, receipt: RequestReceipt
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            command = reconciliation.command
            original = self._ledger_entry(connection, command.reservation_id)
            if (
                original != reconciliation.original_entry
                or original.run_id != run.state.run_id
                or original.state != "unknown"
            ):
                raise ServiceError(
                    "RECONCILIATION_STALE", "Unknown reservation changed or belongs to another run"
                )
            unit = connection.execute(
                "SELECT * FROM execution_units WHERE operation_id=?", (original.operation_id,)
            ).fetchone()
            if (
                unit is None
                or unit["reservation_id"] != command.reservation_id
                or unit["state"] != "unknown_outcome"
            ):
                raise ServiceError(
                    "RECONCILIATION_STALE", "Execution is not awaiting reconciliation"
                )
            if command.action == "retry" and unit["attempts"] >= 2:
                raise ServiceError("ATTEMPT_LIMIT", "Execution permits two total attempts")
            if command.action == "retry":
                stored = connection.execute(
                    "SELECT payload_json FROM execution_receipts WHERE operation_id=?",
                    (original.operation_id,),
                ).fetchone()
                if stored is not None:
                    previous = ExecutionReceipt.model_validate_json(stored[0])
                    if (
                        previous.response is not None or previous.settlement is not None
                        or reconciliation.original_receipt != previous
                        or reconciliation.original_receipt_hash
                        != CanonicalSerializer.digest(previous)
                    ):
                        raise ServiceError(
                            "RETRY_UNSAFE", "Retry cannot replace a provider response"
                        )
                    # Archive the complete empty-response receipt in the immutable reconciliation
                    # before permitting a fresh receipt for the authorized retry.
                    connection.execute(
                        "DELETE FROM execution_receipts WHERE operation_id=?",
                        (original.operation_id,),
                    )
            entry = updated(original, state="reserved")
            connection.execute(
                "UPDATE usage_ledger SET state='reserved',payload_json=? WHERE reservation_id=?",
                (entry.model_dump_json(), entry.reservation_id),
            )
            self._settle(connection, entry.reservation_id, command.settlement)
            result = (
                reconciliation.recovered_receipt.model_dump_json()
                if reconciliation.recovered_receipt is not None
                else None
            )
            state = (
                "succeeded"
                if result is not None
                else "failed"
                if command.action == "retry"
                else "abandoned"
            )
            connection.execute(
                (
                    "UPDATE execution_units SET state=?,result_json=?,result_sha256=?,"
                    "active_milliseconds=active_milliseconds+? WHERE operation_id=?"
                ),
                (
                    state,
                    result,
                    hashlib.sha256(result.encode()).hexdigest() if result is not None else None,
                    command.settlement.actual.active_milliseconds,
                    original.operation_id,
                ),
            )
            self._append_audit(
                connection,
                "usage_reconciliations",
                reconciliation.reconciliation_id,
                run.state.run_id,
                reconciliation,
            )
            self._save_record(
                connection,
                run,
                command.expected_revision,
                "Unknown usage reconciled",
                receipt=receipt,
            )
            connection.commit()

    def resubmit_review(
        self,
        run: RunRecord,
        submission: ReviewResubmission,
        revocations: tuple[ReviewRevocation, ...],
        receipt: RequestReceipt,
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            snapshot = self._budget(connection, run.state.run_id)
            if any(e.state != "settled" for e in snapshot.entries):
                raise ServiceError(
                    "EXECUTION_UNRESOLVED",
                    "Resolve active or unknown execution before resubmitting",
                )
            for revocation in revocations:
                connection.execute(
                    "INSERT INTO review_revocations VALUES(?,?,?)",
                    (revocation.decision_id, revocation.run_id, revocation.model_dump_json()),
                )
            self._append_audit(
                connection,
                "review_resubmissions",
                submission.resubmission_id,
                run.state.run_id,
                submission,
            )
            self._save_record(
                connection,
                run,
                submission.command.expected_revision,
                "Revoked review resubmitted",
                enqueue=True,
                receipt=receipt,
            )
            connection.commit()

    def budget(self, run_id: str) -> BudgetSnapshot:
        with self.connection() as connection:
            return self._budget(connection, run_id)

    def reserve_operation(self, request: OperationReservation) -> str:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute(
                "SELECT payload_json FROM workflow_runs WHERE run_id=?", (request.run_id,)
            ).fetchone()
            if run_row is None:
                raise ServiceError("RUN_NOT_FOUND", "Run does not exist", 404)
            run = RunRecord.model_validate_json(run_row[0])
            if run.state.status not in ("running", "queued"):
                raise ServiceError("RUN_NOT_EXECUTABLE", "Stopped runs cannot start operations")
            if not request.operation_id.startswith(request.run_id + ":"):
                raise ServiceError("EXECUTION_SCOPE_INVALID", "Operation must belong to its run")
            self._budget_policy(connection, request.run_id)
            row = connection.execute(
                "SELECT * FROM execution_units WHERE operation_id=?", (request.operation_id,)
            ).fetchone()
            if (
                request.group_key is not None
                and request.maximum_group_operations is not None
                and row is None
            ):
                if not request.group_key.startswith(
                    request.run_id + ":"
                ) or not request.operation_id.startswith(request.group_key):
                    raise ServiceError(
                        "EXECUTION_SCOPE_INVALID", "Operation is outside its bounded group"
                    )
                count = connection.execute(
                    "SELECT COUNT(*) FROM execution_units WHERE substr(operation_id,1,?)=?",
                    (len(request.group_key), request.group_key),
                ).fetchone()[0]
                if count >= request.maximum_group_operations:
                    raise ServiceError(
                        "RESEARCH_OPERATION_LIMIT",
                        "The frozen question operation limit is exhausted",
                    )
            if row:
                if row["input_hash"] != request.input_hash:
                    raise ServiceError("EXECUTION_INPUT_CHANGED", "Execution dependencies changed")
                if row["state"] != "failed":
                    raise ServiceError(
                        "OUTCOME_UNKNOWN", "Execution is already active or needs reconciliation"
                    )
                if row["attempts"] >= 2:
                    raise ServiceError("ATTEMPT_LIMIT", "Execution permits two total attempts")
            paid = (
                request.reserved.model_requests
                or request.reserved.input_tokens
                or request.reserved.output_tokens
                or request.reserved.cost_microusd
                or request.reserved.search_requests
                or request.reserved.fetch_requests
            )
            if paid and request.price_reference is None:
                raise ServiceError(
                    "PRICE_REQUIRED", "External usage requires a pinned price reference"
                )
            snapshot = self._budget(connection, request.run_id)
            if not snapshot.used.plus(snapshot.held).plus(request.reserved).fits(snapshot.limit):
                raise ServiceError(
                    "BUDGET_EXHAUSTED", "Reservation exceeds the remaining run budget"
                )
            attempt = int(row["attempts"]) + 1 if row else 1
            reservation_id = request.operation_id + ":attempt-" + str(attempt)
            entry = LedgerEntry(
                reservation_id=reservation_id,
                operation_id=request.operation_id,
                run_id=request.run_id,
                state="reserved",
                reserved=request.reserved,
                settlement=None,
                price_reference=request.price_reference,
            )
            connection.execute(
                "INSERT INTO usage_ledger VALUES(?,?,?,?,?)",
                (
                    reservation_id,
                    request.operation_id,
                    request.run_id,
                    entry.state,
                    entry.model_dump_json(),
                ),
            )
            connection.execute(
                (
                    "INSERT INTO execution_units(operation_id,state,input_hash,attempt"
                    "s,reservation_id) VALUES(?,'running',?,?,?) ON CONFLICT(operation"
                    "_id) DO UPDATE SET state='running',attempts=excluded.attempts,res"
                    "ervation_id=excluded.reservation_id"
                ),
                (request.operation_id, request.input_hash, attempt, reservation_id),
            )
            connection.commit()
            return reservation_id

    @staticmethod
    def _reviews(connection: sqlite3.Connection, run_id: str) -> tuple[ReviewDecision, ...]:
        return tuple(
            ReviewDecision.model_validate_json(row[0])
            for row in connection.execute(
                "SELECT payload_json FROM review_decisions WHERE run_id=? ORDER BY rowid", (run_id,)
            ).fetchall()
        )

    def reviews(self, run_id: str) -> tuple[ReviewDecision, ...]:
        with self.connection() as connection:
            return self._reviews(connection, run_id)

    def revoked_reviews(self, run_id: str) -> tuple[str, ...]:
        with self.connection() as connection:
            return tuple(
                row[0]
                for row in connection.execute(
                    "SELECT decision_id FROM review_revocations WHERE run_id=?", (run_id,)
                ).fetchall()
            )

    def revoke_review(
        self,
        run: RunRecord,
        previous_revision: int,
        revocation: ReviewRevocation,
        receipt: RequestReceipt,
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._save_record(connection, run, previous_revision, "Review revoked", receipt=receipt)
            connection.execute(
                "INSERT INTO review_revocations VALUES(?,?,?)",
                (revocation.decision_id, revocation.run_id, revocation.model_dump_json()),
            )
            rows = connection.execute(
                "SELECT payload_json FROM releases WHERE project_id=? AND status='published'",
                (run.state.project_id,),
            ).fetchall()
            for row in rows:
                release = ReleaseRecord.model_validate_json(row[0])
                if revocation.decision_id in release.manifest.review_decision_ids:
                    release = updated(release, status="retired")
                    connection.execute(
                        "UPDATE releases SET status='retired',payload_json=? WHERE release_id=?",
                        (release.model_dump_json(), release.manifest.release_id),
                    )
                    connection.execute(
                        "DELETE FROM project_releases WHERE project_id=? AND release_id=?",
                        (run.state.project_id, release.manifest.release_id),
                    )
            connection.commit()

    def current_release(self, project_id: str) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT release_id FROM project_releases WHERE project_id=?", (project_id,)
            ).fetchone()
        return str(row[0]) if row else None

    def prepare_release(self, release: ReleaseRecord) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT payload_json FROM releases WHERE release_id=?",
                (release.manifest.release_id,),
            ).fetchone()
            if previous:
                recorded = ReleaseRecord.model_validate_json(previous[0])
                if (
                    recorded.manifest != release.manifest
                    or recorded.expected_old_release != release.expected_old_release
                ):
                    raise ServiceError("RELEASE_IMMUTABLE", "Release plan cannot change")
            else:
                connection.execute(
                    "INSERT INTO releases VALUES(?,?,?,?,?)",
                    (
                        release.manifest.release_id,
                        release.manifest.project_id,
                        release.manifest.run_id,
                        release.status,
                        release.model_dump_json(),
                    ),
                )
            connection.commit()

    def release(self, release_id: str) -> ReleaseRecord:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM releases WHERE release_id=?", (release_id,)
            ).fetchone()
        if row is None:
            raise ServiceError("RELEASE_MISSING", "Release was not prepared", 404)
        return ReleaseRecord.model_validate_json(row[0])

    def commit_release(self, run: RunRecord, release: ReleaseRecord) -> RunRecord:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            stored = connection.execute(
                "SELECT payload_json FROM releases WHERE release_id=?",
                (release.manifest.release_id,),
            ).fetchone()
            if stored is None:
                raise ServiceError("RELEASE_STALE", "Release plan is missing")
            recorded = ReleaseRecord.model_validate_json(stored[0])
            if recorded.status == "published" and recorded.manifest == release.manifest:
                current_run = connection.execute(
                    "SELECT payload_json FROM workflow_runs WHERE run_id=?", (run.state.run_id,)
                ).fetchone()
                if current_run:
                    completed = RunRecord.model_validate_json(current_run[0])
                    if (
                        completed.state.status == "published"
                        and completed.current_release_id == release.manifest.release_id
                    ):
                        return completed
            if recorded != release:
                raise ServiceError("RELEASE_STALE", "Release plan changed or was retired")
            pointer = connection.execute(
                "SELECT release_id FROM project_releases WHERE project_id=?",
                (run.state.project_id,),
            ).fetchone()
            current = str(pointer[0]) if pointer else None
            if current != release.expected_old_release:
                raise ServiceError(
                    "RELEASE_CONFLICT", "Project release changed; refusing to overwrite it"
                )
            if (
                release.status != "staged"
                or release.manifest.run_id != run.state.run_id
                or release.manifest.runtime_ref != run.state.runtime_ref
            ):
                raise ServiceError("RELEASE_STALE", "Release does not match the current run")
            revoked = {
                row[0]
                for row in connection.execute(
                    "SELECT decision_id FROM review_revocations WHERE run_id=?", (run.state.run_id,)
                ).fetchall()
            }
            decisions = {item.decision_id for item in self._reviews(connection, run.state.run_id)}
            if not set(release.manifest.review_decision_ids) <= decisions or revoked.intersection(
                release.manifest.review_decision_ids
            ):
                raise ServiceError("REVIEW_REVOKED", "Publication review is missing or revoked")
            if run.environment != "test" or release.manifest.environment != "test":
                raise ServiceError("PUBLICATION_NOT_READY", "Production publication is disabled")
            if release.manifest.project_id != run.state.project_id:
                raise ServiceError("RELEASE_STALE", "Release belongs to another project")
            ReviewSnapshot(
                environment=run.environment,
                required_targets=tuple(
                    target for request in run.review_requests for target in request.targets
                ),
                decisions=tuple(
                    decision
                    for decision in self._reviews(connection, run.state.run_id)
                    if decision.decision_id in release.manifest.review_decision_ids
                ),
            )
            if run.state.status != "running" or run.state.node != "publish_package":
                raise ServiceError("RUN_NOT_EXECUTABLE", "Run cannot publish")
            result = updated(
                run,
                current_release_id=release.manifest.release_id,
                state=updated(run.state, revision=run.state.revision + 1, status="published"),
            )
            self._save_record(
                connection, result, run.state.revision, "Private test release committed"
            )
            published = updated(release, status="published")
            connection.execute(
                "UPDATE releases SET status='published',payload_json=? WHERE release_id=?",
                (published.model_dump_json(), release.manifest.release_id),
            )
            connection.execute(
                (
                    "INSERT INTO project_releases VALUES(?,?) ON CONFLICT(project_id) "
                    "DO UPDATE SET release_id=excluded.release_id"
                ),
                (run.state.project_id, release.manifest.release_id),
            )
            connection.commit()
            return result

    def current_releases(self) -> tuple[ReleaseRecord, ...]:
        with self.connection() as connection:
            return tuple(
                ReleaseRecord.model_validate_json(row[0])
                for row in connection.execute(
                    "SELECT releases.payload_json FROM project_releases "
                    "JOIN releases USING(release_id)"
                ).fetchall()
            )

    def retire_release(self, release_id: str, reason: str) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM releases WHERE release_id=?", (release_id,)
            ).fetchone()
            if row is None:
                raise ServiceError("RELEASE_MISSING", "Release does not exist")
            record = updated(ReleaseRecord.model_validate_json(row[0]), status="retired")
            connection.execute(
                "UPDATE releases SET status='retired',payload_json=? WHERE release_id=?",
                (record.model_dump_json(), release_id),
            )
            connection.execute(
                "DELETE FROM project_releases WHERE project_id=? AND release_id=?",
                (record.manifest.project_id, release_id),
            )
            run = connection.execute(
                "SELECT payload_json FROM workflow_runs WHERE run_id=?", (record.manifest.run_id,)
            ).fetchone()
            if run:
                self._event(connection, RunRecord.model_validate_json(run[0]), reason)
            connection.commit()
