"""Durable grant reservations: uncertain dispatch consumes its slot until reconciled."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pastport_pdf_vr.domain.execution import (
    ExecutionDenied,
    ExecutionInput,
    ExecutionOutput,
    ExecutionRecoveryRequired,
    ModelExecutionError,
    SubscriptionGrant,
)
from pastport_pdf_vr.ports.execution import SemanticTransport


class SubscriptionExecutor:
    def __init__(self, path: Path, grant: SubscriptionGrant, transport: SemanticTransport) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path, self.grant, self._transport = path, grant, transport
        with self._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS execution_grants (
                project TEXT NOT NULL, grant_ref TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(project,grant_ref))""")
            db.execute("""CREATE TABLE IF NOT EXISTS executions (
                project TEXT NOT NULL, grant_ref TEXT NOT NULL, binding TEXT NOT NULL,
                state TEXT NOT NULL, result TEXT, error_type TEXT,
                PRIMARY KEY(project,grant_ref,binding))""")
            existing = db.execute(
                "SELECT payload FROM execution_grants WHERE project=? AND grant_ref=?",
                (grant.project_id, grant.grant_ref),
            ).fetchone()
            if existing and existing[0] != grant.model_dump_json():
                raise ExecutionDenied("An existing grant cannot be silently changed or reset")
            db.execute(
                "INSERT OR IGNORE INTO execution_grants VALUES (?,?,?)",
                (grant.project_id, grant.grant_ref, grant.model_dump_json()),
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db: sqlite3.Connection | None = None
        try:
            db = sqlite3.connect(self._path, timeout=10)
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        except sqlite3.Error as error:
            raise ModelExecutionError("Execution ledger unavailable") from error
        finally:
            if db is not None:
                db.close()

    def remaining_calls(self) -> int:
        with self._connection() as db:
            rows = db.execute(
                "SELECT state,result FROM executions WHERE project=? AND grant_ref=?",
                (self.grant.project_id, self.grant.grant_ref),
            ).fetchall()
        if any(row[0] != "completed" for row in rows):
            raise ExecutionRecoveryRequired("Unknown prior usage blocks further dispatch")
        tokens = sum(ExecutionOutput.model_validate_json(row[1]).total_tokens for row in rows)
        if tokens >= self.grant.max_recorded_tokens:
            return 0
        return max(0, self.grant.max_calls - len(rows))

    def remaining_recorded_tokens(self) -> int:
        with self._connection() as db:
            rows = db.execute(
                "SELECT state,result FROM executions WHERE project=? AND grant_ref=?",
                (self.grant.project_id, self.grant.grant_ref),
            ).fetchall()
        if any(row[0] != "completed" for row in rows):
            raise ExecutionRecoveryRequired("Unknown prior usage blocks further dispatch")
        used = sum(ExecutionOutput.model_validate_json(row[1]).total_tokens for row in rows)
        return max(0, self.grant.max_recorded_tokens - used)

    def execute(self, request: ExecutionInput) -> ExecutionOutput:
        grant = self.grant
        if (request.project_id, request.grant_ref, request.model_id) != (
            grant.project_id,
            grant.grant_ref,
            grant.model_id,
        ):
            raise ExecutionDenied("Request does not match its execution grant")
        if len(request.image_paths) != len(request.image_hashes) or len(request.image_paths) > 8:
            raise ExecutionDenied("Image bindings are incomplete or oversized")
        binding = hashlib.sha256((request.model_dump_json() + grant.effort).encode()).hexdigest()
        key = (grant.project_id, grant.grant_ref, binding)
        with self._connection() as db:
            previous = db.execute(
                "SELECT state,result FROM executions WHERE project=? AND grant_ref=? AND binding=?",
                key,
            ).fetchone()
            if previous:
                if previous[0] == "completed":
                    return ExecutionOutput.model_validate_json(previous[1])
                raise ExecutionRecoveryRequired("Prior dispatch needs reconciliation; not retried")
            rows = db.execute(
                "SELECT state,result FROM executions WHERE project=? AND grant_ref=?",
                key[:2],
            ).fetchall()
            if any(row[0] != "completed" for row in rows):
                raise ExecutionRecoveryRequired("Unknown prior usage blocks further dispatch")
            used_tokens = sum(
                ExecutionOutput.model_validate_json(row[1]).total_tokens for row in rows
            )
            if len(rows) >= grant.max_calls or used_tokens >= grant.max_recorded_tokens:
                raise ExecutionDenied("Subscription grant call/token threshold reached")
            db.execute("INSERT INTO executions VALUES (?,?,?,'dispatching',NULL,NULL)", key)
        try:
            result = self._transport.execute(request, grant.timeout_seconds)
            # Receipt identity belongs to this executor, never to generated JSON.
            result = result.model_copy(update={"receipt_ref": "codex:" + binding})
        except BaseException as error:
            # Cancellation, interruption and transport failure may all have consumed quota.
            with self._connection() as db:
                db.execute(
                    "UPDATE executions SET state='recovery_required',error_type=? "
                    "WHERE project=? AND grant_ref=? AND binding=?",
                    (type(error).__name__, *key),
                )
            raise
        with self._connection() as db:
            db.execute(
                "UPDATE executions SET state='completed',result=? WHERE project=? AND "
                "grant_ref=? AND binding=?",
                (result.model_dump_json(), *key),
            )
        return result
