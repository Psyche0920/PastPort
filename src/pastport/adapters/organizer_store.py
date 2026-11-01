"""Closed-connection SQLite metadata store for Organizer, independent of review data."""

import fcntl
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import TypeVar

from pastport.application.models import ServiceError
from pastport.domain.common import Contract

Record = TypeVar("Record", bound=Contract)


class OrganizerStore:
    """Separate production-job metadata; never a replacement evidence-review database."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "organizer.sqlite3"
        with self.connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, "
                "payload TEXT NOT NULL, PRIMARY KEY(kind,id))"
            )

    @contextmanager
    def ownership(self) -> Iterator[None]:
        with (self.directory / ".service.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ServiceError(
                    "ORGANIZER_ALREADY_RUNNING", "此制作目录已由另一服务使用。", 503
                ) from error
            yield

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            yield connection

    def get(self, kind: str, key: str, model: type[Record]) -> Record:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
        if row is None:
            raise ServiceError("ORGANIZER_NOT_FOUND", "找不到此项目或制作记录。", 404)
        return model.model_validate_json(row[0])

    def list(self, kind: str, model: type[Record]) -> tuple[Record, ...]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM records WHERE kind=? ORDER BY rowid DESC", (kind,)
            ).fetchall()
        return tuple(model.model_validate_json(row[0]) for row in rows)

    def save(self, kind: str, key: str, value: Contract) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) "
                "DO UPDATE SET payload=excluded.payload",
                (kind, key, value.model_dump_json()),
            )
