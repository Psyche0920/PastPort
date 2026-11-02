"""Durable grant reservations: uncertain dispatch consumes its slot until reconciled."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pastport_evidence.domain.execution import (
    ExecutionDenied,
    ExecutionInput,
    ExecutionOutput,
    ExecutionRecoveryRequired,
    ModelExecutionError,
    SubscriptionGrant,
)
from pastport_evidence.ports.execution import SemanticTransport


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
            db.execute("""CREATE TABLE IF NOT EXISTS execution_failures (
                project TEXT NOT NULL, grant_ref TEXT NOT NULL, binding TEXT NOT NULL,
                error_type TEXT NOT NULL, failure_code TEXT NOT NULL, cause_type TEXT,
                PRIMARY KEY(project,grant_ref,binding))""")
            db.execute("""CREATE TABLE IF NOT EXISTS execution_recoveries (
                project TEXT NOT NULL, grant_ref TEXT NOT NULL, binding TEXT NOT NULL,
                replacement_binding TEXT NOT NULL, reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(project,grant_ref,binding))""")
            db.execute("""CREATE TABLE IF NOT EXISTS execution_budget_amendments (
                project TEXT NOT NULL, grant_ref TEXT NOT NULL, token_limit INTEGER NOT NULL,
                reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
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

    def authorize_token_limit(self, limit: int, reason: str) -> None:
        """Append explicit budget authorization without rewriting the original grant."""
        if not reason.strip() or not self.grant.max_recorded_tokens < limit <= 1_000_000:
            raise ValueError("Explicit token increase must stay within one million")
        with self._connection() as db:
            db.execute("INSERT INTO execution_budget_amendments(project,grant_ref,token_limit,reason) VALUES (?,?,?,?)", (self.grant.project_id, self.grant.grant_ref, limit, reason))

    def remove_token_threshold(self, reason: str) -> None:
        """Apply a run-specific authorized override; preserve usage and call ceilings."""
        if not reason.strip():
            raise ValueError("Authorization reason required")
        if self._token_limit() == 0:
            return
        with self._connection() as db:
            db.execute("INSERT INTO execution_budget_amendments(project,grant_ref,token_limit,reason) VALUES (?,?,0,?)", (self.grant.project_id,self.grant.grant_ref,reason))

    def _token_limit(self) -> int:
        with self._connection() as db:
            row = db.execute("SELECT token_limit FROM execution_budget_amendments WHERE project=? AND grant_ref=? ORDER BY rowid DESC LIMIT 1", (self.grant.project_id,self.grant.grant_ref)).fetchone()
        return int(row[0]) if row else self.grant.max_recorded_tokens

    def approve_interrupted_retry(self, binding: str, reason: str) -> None:
        """Authorize one replacement; keep original dispatch and unknown usage intact."""
        if not reason.strip():
            raise ValueError("Manual recovery requires an audit reason")
        key = (self.grant.project_id, self.grant.grant_ref, binding)
        with self._connection() as db:
            row = db.execute("SELECT state FROM executions WHERE project=? AND grant_ref=? AND binding=?", key).fetchone()
            if row is None or row[0] not in ("dispatching", "recovery_required"):
                raise ExecutionRecoveryRequired("Only an interrupted dispatch can be approved")
            replacement = hashlib.sha256((binding + ":manual-retry-v1").encode()).hexdigest()
            db.execute("INSERT OR IGNORE INTO execution_recoveries(project,grant_ref,binding,replacement_binding,reason) VALUES (?,?,?,?,?)", (*key, replacement, reason))

    def _approved(self, db: sqlite3.Connection) -> set[str]:
        return {str(row[0]) for row in db.execute("SELECT binding FROM execution_recoveries WHERE project=? AND grant_ref=?", (self.grant.project_id, self.grant.grant_ref))}

    def remaining_calls(self) -> int:
        with self._connection() as db:
            rows = db.execute(
                "SELECT state,result,binding FROM executions WHERE project=? AND grant_ref=?",
                (self.grant.project_id, self.grant.grant_ref),
            ).fetchall()
            approved = self._approved(db)
        if any(row[0] != "completed" and row[2] not in approved for row in rows):
            raise ExecutionRecoveryRequired("Unknown prior usage blocks further dispatch")
        tokens = sum(ExecutionOutput.model_validate_json(row[1]).total_tokens for row in rows if row[0] == "completed")
        limit = self._token_limit()
        if limit != 0 and tokens >= limit:
            return 0
        return max(0, self.grant.max_calls - len(rows))

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
        token_limit = self._token_limit()
        with self._connection() as db:
            for _ in range(grant.max_calls):
                replacement = db.execute("SELECT replacement_binding FROM execution_recoveries WHERE project=? AND grant_ref=? AND binding=?", key).fetchone()
                if replacement is None:
                    break
                binding = str(replacement[0])
                key = (grant.project_id, grant.grant_ref, binding)
            previous = db.execute(
                "SELECT state,result FROM executions WHERE project=? AND grant_ref=? AND binding=?",
                key,
            ).fetchone()
            if previous:
                if previous[0] == "completed":
                    return ExecutionOutput.model_validate_json(previous[1])
                raise ExecutionRecoveryRequired("Prior dispatch needs reconciliation; not retried")
            rows = db.execute(
                "SELECT state,result,binding FROM executions WHERE project=? AND grant_ref=?",
                key[:2],
            ).fetchall()
            if any(row[0] != "completed" and row[2] not in self._approved(db) for row in rows):
                raise ExecutionRecoveryRequired("Unknown prior usage blocks further dispatch")
            used_tokens = sum(
                ExecutionOutput.model_validate_json(row[1]).total_tokens for row in rows if row[0] == "completed"
            )
            if len(rows) >= grant.max_calls or (token_limit != 0 and used_tokens >= token_limit):
                raise ExecutionDenied("Subscription grant call/token threshold reached")
            db.execute("INSERT INTO executions VALUES (?,?,?,'dispatching',NULL,NULL)", key)
        try:
            timeout = min(grant.timeout_seconds, 120) if (
                request.kind == "photo_inspection" and request.prompt_version in ("v2", "v3")
            ) else grant.timeout_seconds
            result = self._transport.execute(request, timeout)
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
                code = error.failure_code if isinstance(error, ModelExecutionError) else "execution_failed"
                db.execute(
                    "INSERT OR REPLACE INTO execution_failures VALUES (?,?,?,?,?,?)",
                    (*key, type(error).__name__, code,
                     type(error.__cause__).__name__ if error.__cause__ else None),
                )
            raise
        with self._connection() as db:
            db.execute(
                "UPDATE executions SET state='completed',result=? WHERE project=? AND "
                "grant_ref=? AND binding=?",
                (result.model_dump_json(), *key),
            )
        return result
