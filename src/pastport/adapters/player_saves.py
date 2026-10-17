"""Durable, version-checked SQLite saves with one transaction for state and receipts."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from pastport.application.player_runtime import PlayerRuntimeError
from pastport.domain.common import CanonicalSerializer
from pastport.domain.game import PlayerState
from pastport.domain.player_saves import PlayerSaveKey

MAXIMUM_STATE_BYTES = 4 * 1024 * 1024


class SQLitePlayerSaves:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PlayerRuntimeError(
                "SAVE_STORAGE_FAILED", "Player storage is unavailable"
            ) from error
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise PlayerRuntimeError(
                    "SAVE_VERSION_UNSUPPORTED", "Player storage requires an explicit migration"
                )
            if version == 0:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if tables:
                    raise PlayerRuntimeError(
                        "SAVE_VERSION_UNSUPPORTED", "Refusing to replace an unrecognized database"
                    )
                connection.execute("""CREATE TABLE player_saves (
                    environment TEXT NOT NULL, actor_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, save_id TEXT NOT NULL,
                    release_id TEXT NOT NULL, package_hash TEXT NOT NULL,
                    chapter_id TEXT NOT NULL, schema_version TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 0),
                    state_json TEXT NOT NULL, state_sha256 TEXT NOT NULL,
                    PRIMARY KEY(environment, actor_id, project_id, save_id)
                )""")
                connection.execute("PRAGMA user_version=1")
            connection.commit()
            connection.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA synchronous=FULL")
                yield connection
            finally:
                try:
                    if connection.in_transaction:
                        connection.rollback()
                finally:
                    connection.close()
        except sqlite3.Error as error:
            raise PlayerRuntimeError(
                "SAVE_STORAGE_FAILED", "Player storage operation failed"
            ) from error

    @staticmethod
    def _key(key: PlayerSaveKey) -> tuple[str, str, str, str]:
        return key.environment, key.actor_id, key.project_id, key.save_id

    @staticmethod
    def _identity(state: PlayerState) -> tuple[str, str, str, str, str]:
        return (
            state.project_id,
            state.release_id,
            state.package_hash,
            state.chapter_id,
            state.schema_version,
        )

    @staticmethod
    def _encode(key: PlayerSaveKey, state: PlayerState) -> tuple[str, str]:
        if key.project_id != state.project_id:
            raise PlayerRuntimeError("SAVE_IDENTITY_MISMATCH", "Save belongs to another project")
        encoded = state.model_dump_json()
        if len(encoded.encode("utf-8")) > MAXIMUM_STATE_BYTES:
            raise PlayerRuntimeError("SAVE_TOO_LARGE", "Save exceeds the storage byte limit")
        return encoded, CanonicalSerializer.digest(state)

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> PlayerState | None:
        if row is None:
            return None
        encoded = row["state_json"]
        if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > MAXIMUM_STATE_BYTES:
            raise PlayerRuntimeError("SAVE_CORRUPT", "Stored player state exceeds its bounds")
        try:
            state = PlayerState.model_validate_json(encoded)
        except ValidationError as error:
            raise PlayerRuntimeError(
                "SAVE_CORRUPT", "Stored player state failed validation"
            ) from error
        if (
            CanonicalSerializer.digest(state) != row["state_sha256"]
            or state.project_id != row["project_id"]
            or state.release_id != row["release_id"]
            or state.package_hash != row["package_hash"]
            or state.chapter_id != row["chapter_id"]
            or state.schema_version != row["schema_version"]
            or state.revision != row["revision"]
        ):
            raise PlayerRuntimeError(
                "SAVE_CORRUPT", "Stored player state failed its identity or content check"
            )
        return state

    def load(self, key: PlayerSaveKey) -> PlayerState | None:
        with self._connection() as connection:
            return self._decode(
                connection.execute(
                    "SELECT * FROM player_saves WHERE environment=? AND actor_id=? "
                    "AND project_id=? AND save_id=?",
                    self._key(key),
                ).fetchone()
            )

    def create(self, key: PlayerSaveKey, state: PlayerState) -> PlayerState:
        if state.revision != 0 or state.processed_actions:
            raise PlayerRuntimeError(
                "SAVE_INITIAL_STATE_REQUIRED", "New saves require an initial player state"
            )
        encoded, digest = self._encode(key, state)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO player_saves VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(environment, actor_id, project_id, save_id) DO NOTHING""",
                (
                    *self._key(key),
                    state.release_id,
                    state.package_hash,
                    state.chapter_id,
                    state.schema_version,
                    state.revision,
                    encoded,
                    digest,
                ),
            )
            stored = self._decode(
                connection.execute(
                    "SELECT * FROM player_saves WHERE environment=? AND actor_id=? "
                    "AND project_id=? AND save_id=?",
                    self._key(key),
                ).fetchone()
            )
            if stored is None or self._identity(stored) != self._identity(state):
                raise PlayerRuntimeError(
                    "SAVE_IDENTITY_MISMATCH",
                    "Save belongs to another release; choose an explicit new save ID",
                )
            connection.commit()
            return stored

    def compare_and_swap(
        self, key: PlayerSaveKey, previous: PlayerState, following: PlayerState
    ) -> bool:
        if (
            self._identity(previous) != self._identity(following)
            or following.revision != previous.revision + 1
            or len(following.processed_actions) != len(previous.processed_actions) + 1
            or following.processed_actions[:-1] != previous.processed_actions
        ):
            raise PlayerRuntimeError(
                "SAVE_TRANSITION_INVALID",
                "State and receipt must advance together without replacing history",
            )
        encoded, digest = self._encode(key, following)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE player_saves SET revision=?, state_json=?, state_sha256=?
                WHERE environment=? AND actor_id=? AND project_id=? AND save_id=?
                AND revision=? AND state_sha256=? AND release_id=? AND package_hash=?
                AND chapter_id=? AND schema_version=?""",
                (
                    following.revision,
                    encoded,
                    digest,
                    *self._key(key),
                    previous.revision,
                    CanonicalSerializer.digest(previous),
                    previous.release_id,
                    previous.package_hash,
                    previous.chapter_id,
                    previous.schema_version,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
