"""Build and validate the portable SQLite content database."""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, cast


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.story_import import ChapterRecord, NarrativeImporter, StoryImportError


class DatabaseBuildError(RuntimeError):
    """Raised when the content database cannot be built safely."""


@dataclass(frozen=True)
class BuildConfig:
    schema_path: Path
    seed_path: Path
    media_manifest_path: Path
    drive_file_ids_path: Path
    database_path: Path
    replace_existing: bool = False


@dataclass(frozen=True)
class MediaManifestEntry:
    asset_id: str
    site_id: str
    source_id: str
    filename: str
    media_type: str
    observed_content: str
    mapping_state: str
    rights_state: str
    alt_text: str
    structure_id: str

    @classmethod
    def from_row(cls, row: Dict[str, Optional[str]]) -> "MediaManifestEntry":
        required_fields = (
            "asset_id", "site_id", "source_id", "filename", "media_type",
            "observed_content", "mapping_state", "rights_state", "alt_text", "structure_id",
        )
        missing = [field for field in required_fields if row.get(field) is None]
        if missing:
            raise DatabaseBuildError(f"Photo manifest row is missing fields: {missing}")
        return cls(**{field: cast(str, row[field]) for field in required_fields})


@dataclass(frozen=True)
class DriveFileReference:
    filename: str
    drive_file_id: str

    @classmethod
    def from_row(cls, row: Dict[str, Optional[str]]) -> "DriveFileReference":
        filename = row.get("filename")
        drive_file_id = row.get("drive_file_id")
        if not filename or not drive_file_id:
            raise DatabaseBuildError("Drive file reference needs a filename and file ID.")
        return cls(filename=filename, drive_file_id=drive_file_id)


class DatabaseBuilder:
    """Create a fresh SQLite database and enforce basic editorial invariants."""

    def build(self, config: BuildConfig) -> Path:
        if config.database_path.exists() and not config.replace_existing:
            raise DatabaseBuildError(
                f"{config.database_path} already exists; pass --replace to rebuild it."
            )

        try:
            schema = config.schema_path.read_text(encoding="utf-8")
            seed = config.seed_path.read_text(encoding="utf-8")
            with config.media_manifest_path.open(encoding="utf-8", newline="") as manifest_file:
                reader = csv.DictReader(manifest_file)
                media_entries = [MediaManifestEntry.from_row(row) for row in reader]
            with config.drive_file_ids_path.open(encoding="utf-8", newline="") as ids_file:
                reader = csv.DictReader(ids_file)
                drive_references = [DriveFileReference.from_row(row) for row in reader]
        except OSError as error:
            raise DatabaseBuildError(f"Could not read SQL input: {error}") from error
        except csv.Error as error:
            raise DatabaseBuildError(f"Could not read photo manifest: {error}") from error
        reference_names = [reference.filename for reference in drive_references]
        reference_ids = [reference.drive_file_id for reference in drive_references]
        if len(reference_names) != len(media_entries):
            raise DatabaseBuildError("Photo manifest and Drive ID list must contain the same number of files.")
        if len(set(reference_names)) != len(reference_names) or len(set(reference_ids)) != len(reference_ids):
            raise DatabaseBuildError("Drive photo filenames and IDs must both be unique.")

        config.database_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="pastport-", suffix=".sqlite3", dir=config.database_path.parent, delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
            with closing(sqlite3.connect(temporary_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executescript(schema)
                connection.executescript(seed)
                connection.executemany(
                    """INSERT OR IGNORE INTO media_assets
                       (asset_id, site_id, source_id, filename, media_type, observed_content,
                        mapping_state, rights_state, alt_text, structure_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            entry.asset_id, entry.site_id, entry.source_id, entry.filename,
                            entry.media_type, entry.observed_content, entry.mapping_state,
                            entry.rights_state, entry.alt_text, entry.structure_id or None,
                        )
                        for entry in media_entries
                    ],
                )
                connection.executemany(
                    "UPDATE media_assets SET source_file_id = ? WHERE filename = ? AND source_id = 'src-drive-photos'",
                    [(reference.drive_file_id, reference.filename) for reference in drive_references],
                )
                record = ChapterRecord.read(config.schema_path.parent / "muradiye-story.json")
                NarrativeImporter().import_chapter(connection, record, config.schema_path.parent.parent)
                self._validate(connection)
                connection.commit()
            os.replace(temporary_path, config.database_path)
        except (sqlite3.Error, DatabaseBuildError, StoryImportError, OSError) as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            if isinstance(error, DatabaseBuildError):
                raise
            raise DatabaseBuildError(f"SQLite build failed: {error}") from error
        return config.database_path

    @staticmethod
    def _validate(connection: sqlite3.Connection) -> None:
        violations = list(connection.execute("PRAGMA foreign_key_check"))
        if violations:
            raise DatabaseBuildError(f"Foreign-key violations found: {violations[:3]}")

        required_counts = {
            "sites": 1,
            "sources": 8,
            "heritage_works": 18,
            "claims": 16,
            "media_assets": 93,
            "scene_nodes": 5,
            "story_choices": 3,
            "characters": 2,
            "editorial_review_items": 3,
        }
        for table, expected in required_counts.items():
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            actual = 0 if row is None else int(row[0])
            if actual < expected:
                raise DatabaseBuildError(
                    f"Seed validation failed: {table} has {actual}, expected at least {expected}."
                )

        unreferenced_facts = connection.execute(
            """SELECT c.claim_id FROM claims AS c
               LEFT JOIN claim_sources AS cs ON cs.claim_id = c.claim_id
               WHERE c.claim_kind = 'verified_fact' AND c.publication_state = 'approved'
               GROUP BY c.claim_id HAVING COUNT(cs.source_id) = 0"""
        ).fetchall()
        if unreferenced_facts:
            raise DatabaseBuildError(
                f"Approved historical facts need a source: {unreferenced_facts[:3]}"
            )

        missing_fallbacks = connection.execute(
            """SELECT slot_id FROM task_slots AS slot
               WHERE ai_enabled = 1 AND (
                   fallback_task_id IS NULL OR NOT EXISTS (
                       SELECT 1 FROM task_candidates AS task
                       WHERE task.task_id = slot.fallback_task_id
                         AND task.provider = 'fallback' AND task.state = 'published'
                   )
               )"""
        ).fetchall()
        if missing_fallbacks:
            raise DatabaseBuildError(f"AI-enabled task slots need a published fallback: {missing_fallbacks}")

        missing_drive_ids = connection.execute(
            "SELECT COUNT(*) FROM media_assets WHERE source_id = 'src-drive-photos' AND source_file_id = ''"
        ).fetchone()
        if missing_drive_ids is None or int(missing_drive_ids[0]) > 0:
            raise DatabaseBuildError("Every indexed Drive photo needs its stable file ID.")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "data" / "pastport.sqlite3")
    parser.add_argument("--replace", action="store_true", help="Replace an existing output database.")
    arguments = parser.parse_args()
    config = BuildConfig(
        schema_path=root / "data" / "schema.sql",
        seed_path=root / "data" / "seed.sql",
        media_manifest_path=root / "data" / "media_manifest.csv",
        drive_file_ids_path=root / "data" / "drive_file_ids.csv",
        database_path=arguments.output,
        replace_existing=arguments.replace,
    )
    try:
        output = DatabaseBuilder().build(config)
    except DatabaseBuildError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Built and validated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
