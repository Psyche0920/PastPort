"""Private SQLite preview metadata and atomic player state, outside release storage."""

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from pastport.adapters.player_saves import SQLitePlayerSaves
from pastport.application.models import Actor, ServiceError
from pastport.application.previews import PreviewRecord
from pastport.domain.common import CanonicalSerializer, Environment
from pastport.domain.game import PlayerState
from pastport.domain.player_saves import PlayerSaveKey


class SQLitePreviews(SQLitePlayerSaves):
    def __init__(self, path: Path, environment: Environment) -> None:
        super().__init__(path)
        self.environment = environment
        with self._connection() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS preview_records (
                environment TEXT NOT NULL, actor_id TEXT NOT NULL, project_id TEXT NOT NULL,
                run_id TEXT NOT NULL, preview_id TEXT NOT NULL,
                request_key TEXT NOT NULL, expires_at TEXT NOT NULL,
                payload_json TEXT NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(environment, actor_id, run_id, preview_id),
                UNIQUE(environment, actor_id, run_id, request_key)
            )""")

    @staticmethod
    def save_key(record: PreviewRecord) -> PlayerSaveKey:
        return PlayerSaveKey(
            environment=record.environment,
            actor_id=record.actor_id,
            project_id=record.project_id,
            save_id=record.preview_id,
        )

    @staticmethod
    def decode_record(payload: str, digest: str) -> PreviewRecord:
        if len(payload.encode()) > 12 * 1024 * 1024:
            raise ServiceError("PREVIEW_CORRUPT", "Preview metadata exceeds its bounds")
        try:
            record = PreviewRecord.model_validate_json(payload)
        except ValidationError as error:
            raise ServiceError("PREVIEW_CORRUPT", "Preview metadata failed validation") from error
        if CanonicalSerializer.digest(record) != digest:
            raise ServiceError("PREVIEW_CORRUPT", "Preview metadata failed its hash")
        return record

    def find_request(self, actor: Actor, run_id: str, request_key: str) -> PreviewRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT payload_json,sha256 FROM preview_records
                WHERE environment=? AND actor_id=? AND run_id=? AND request_key=?""",
                (self.environment, actor.actor_id, run_id, request_key),
            ).fetchone()
        if row is None:
            return None
        record = self.decode_record(row[0], row[1])
        if (record.environment, record.actor_id, record.run_id, record.request_key) != (
            self.environment,
            actor.actor_id,
            run_id,
            request_key,
        ):
            raise ServiceError("PREVIEW_CORRUPT", "Preview request identity differs")
        return record

    def get(self, actor: Actor, run_id: str, preview_id: str) -> PreviewRecord:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT payload_json,sha256 FROM preview_records
                WHERE environment=? AND actor_id=? AND run_id=? AND preview_id=?""",
                (self.environment, actor.actor_id, run_id, preview_id),
            ).fetchone()
        if row is None:
            raise ServiceError("PREVIEW_NOT_FOUND", "Preview does not exist for this account", 404)
        record = self.decode_record(row[0], row[1])
        if (record.environment, record.actor_id, record.run_id, record.preview_id) != (
            self.environment,
            actor.actor_id,
            run_id,
            preview_id,
        ):
            raise ServiceError("PREVIEW_CORRUPT", "Preview identity differs")
        return record

    def create_preview(
        self, record: PreviewRecord, state: PlayerState, now: datetime
    ) -> PreviewRecord:
        # Metadata, idempotency binding, quota and initial state share one write transaction.
        if (
            record.environment != self.environment
            or now >= record.expires_at
            or record.runtime_ref.project_id != record.project_id
            or CanonicalSerializer.digest(record.runtime_package) != record.runtime_ref.sha256
            or state.release_id != "preview:" + record.preview_id
            or state.package_hash != record.runtime_ref.sha256
            or state.chapter_id != record.runtime_package.game.chapter_id
            or state.schema_version != record.runtime_package.schema_version
            or state.revision != 0
            or state.processed_actions
        ):
            raise ServiceError(
                "PREVIEW_IDENTITY_MISMATCH", "Initial preview identities or expiry differ"
            )
        encoded, digest = self._encode(self.save_key(record), state)
        payload = record.model_dump_json()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT payload_json,sha256 FROM preview_records
                WHERE environment=? AND actor_id=? AND run_id=? AND request_key=?""",
                (record.environment, record.actor_id, record.run_id, record.request_key),
            ).fetchone()
            if row is not None:
                previous = self.decode_record(row[0], row[1])
                if previous.request_hash != record.request_hash:
                    raise ServiceError(
                        "IDEMPOTENCY_CONFLICT", "Preview request key has another payload"
                    )
                return previous
            count = connection.execute(
                """SELECT count(*) FROM preview_records
                WHERE environment=? AND actor_id=? AND project_id=? AND expires_at>?""",
                (record.environment, record.actor_id, record.project_id, now.isoformat()),
            ).fetchone()[0]
            if count >= 10:
                raise ServiceError("PREVIEW_LIMIT_REACHED", "Ten active previews already exist")
            if len(payload.encode()) > 12 * 1024 * 1024:
                raise ServiceError("PREVIEW_TOO_LARGE", "Preview metadata exceeds its bounds", 413)
            connection.execute(
                "INSERT INTO preview_records VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    record.environment,
                    record.actor_id,
                    record.project_id,
                    record.run_id,
                    record.preview_id,
                    record.request_key,
                    record.expires_at.isoformat(),
                    payload,
                    CanonicalSerializer.digest(record),
                ),
            )
            connection.execute(
                "INSERT INTO player_saves VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    *self._key(self.save_key(record)),
                    state.release_id,
                    state.package_hash,
                    state.chapter_id,
                    state.schema_version,
                    state.revision,
                    encoded,
                    digest,
                ),
            )
            connection.commit()
        return record

    def state(self, record: PreviewRecord) -> PlayerState:
        state = self.load(self.save_key(record))
        if state is None:
            raise ServiceError("PREVIEW_CORRUPT", "Preview state is missing")
        return state

    def commit(
        self, record: PreviewRecord, previous: PlayerState, following: PlayerState, now: datetime
    ) -> bool:
        if now >= record.expires_at:
            raise ServiceError("PREVIEW_EXPIRED", "Preview has expired; create a new session", 410)
        return self.compare_and_swap(self.save_key(record), previous, following)
