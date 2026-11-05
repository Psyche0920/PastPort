"""Persistent-data identity and consistent backups for the shared Organizer host."""

import json
import secrets
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

STORE_MARKER = ".pastport-data-id"
RECORD = "data-identity.json"


class DataIdentityError(ValueError):
    """The configured store is missing or is not the one this deployment used before."""


class DataIdentity:
    """Refuse to replace a known store with a new empty one after a path change or data loss."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.store = directory / "server" / "organizer"
        self.record = directory / RECORD

    def verify(self) -> str:
        marker = self.store / STORE_MARKER
        if self.record.is_file():
            expected = json.loads(self.record.read_text())["organizer"]
            if not marker.is_file() or marker.read_text().strip() != expected:
                raise DataIdentityError(
                    f"Organizer data at {self.store} is missing or is not this deployment's store "
                    f"(expected {expected}). No empty store was created. Restore the backup, or "
                    f"delete {self.record} only if you intend to start over."
                )
            return str(expected)
        if marker.is_file():
            identity = marker.read_text().strip()
        else:
            identity = secrets.token_hex(16)
            self.store.mkdir(parents=True, exist_ok=True)
            marker.write_text(identity + "\n")
        self.record.write_text(json.dumps({"organizer": identity}) + "\n")
        return identity


def _copy_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as origin,
        closing(sqlite3.connect(target)) as copy,
    ):
        origin.backup(copy)


class DeploymentBackup:
    """Online SQLite backups plus immutable game files; restore by pointing a service at it."""

    def __init__(self, directory: Path, player_data: Path) -> None:
        self.directory = directory.resolve()
        self.player_data = player_data.resolve()

    def create(self, output: Path) -> dict[str, object]:
        DataIdentity(self.directory).verify()
        if output.exists():
            raise ValueError(f"Backup target already exists: {output}")
        store = self.directory / "server" / "organizer"
        players = self.player_data / "players.sqlite"
        if not players.is_file():
            raise ValueError(f"Player database not found: {players}")
        target = output / "server" / "organizer"
        target.mkdir(parents=True)
        output.chmod(0o700)
        _copy_database(store / "organizer.sqlite3", target / "organizer.sqlite3")
        for item in store.iterdir():
            if item.name in ("organizer.sqlite3", "delivery-uploads") or item.name.startswith(
                (".service.lock", "organizer.sqlite3-", ".map-")
            ):
                continue
            if item.is_dir():
                shutil.copytree(item, target / item.name, symlinks=True)
            else:
                shutil.copy2(item, target / item.name)
        for name in ("staff-accounts.json", RECORD, "catalog.json"):
            if (self.directory / name).is_file():
                shutil.copy2(self.directory / name, output / name)
        _copy_database(players, output / "player" / "players.sqlite")
        if (self.player_data / STORE_MARKER).is_file():
            shutil.copy2(self.player_data / STORE_MARKER, output / "player" / STORE_MARKER)
        with closing(sqlite3.connect(output / "player" / "players.sqlite")) as database:
            counts = {
                table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("player", "stamp", "game_save")
                if database.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
            }
        with closing(sqlite3.connect(target / "organizer.sqlite3")) as database:
            records = dict(
                database.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind").fetchall()
            )
        summary: dict[str, object] = {
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "organizer_records": records,
            "player_rows": counts,
            "publications": sorted(p.name for p in target.glob("player-map-*.json")),
            "contains_password_hashes": (output / "staff-accounts.json").is_file(),
        }
        (output / "BACKUP.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary
