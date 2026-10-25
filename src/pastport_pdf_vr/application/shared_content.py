"""One content authority per source environment; spatial state remains per result."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from pastport_pdf_vr.application.reference_environment import digest
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.domain.models import DomainModel

# Only semantic tables are shared. Never include 3D/VR positions or navigation.
CONTENT_TABLES = (
    "modern_objects",
    "historical_objects",
    "pairings",
    "passages",
    "source_pages",
    "text_associations",
    "assistant_semantic_audit",
    "photos",
    "observations",
    "design_references",
    "vr_display_contents",
    "vr_content_events",
    "review_events",
)


class ContentBinding(DomainModel):
    schema_version: int = 1
    source_root: str
    import_sha256: str
    identity_sha256: str
    scope: str


class SharedContentConflict(ValueError):
    """Divergent human histories require an explicit editorial decision."""


def identity_hash(db: sqlite3.Connection) -> str:
    rows = db.execute("SELECT id,stable_id FROM modern_objects ORDER BY id").fetchall()
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


class SharedContentAuthority:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / "shared-content.json"

    @property
    def database(self) -> Path:
        if not self.path.is_file():
            return self.root / "pastport_matching.sqlite3"
        binding = ContentBinding.model_validate_json(self.path.read_bytes())
        source = Path(binding.source_root)
        if not source.is_absolute() or source.is_symlink():
            raise ValueError("Invalid shared content source")
        if digest(source / "import-manifest.json") != binding.import_sha256:
            raise ValueError("Shared source import changed")
        if digest(self.root / "import-manifest.json") != binding.import_sha256:
            raise ValueError("Derived input environment changed")
        expected_scope = hashlib.sha256((str(source) + binding.import_sha256).encode()).hexdigest()
        if binding.scope != expected_scope:
            raise ValueError("Shared content scope changed")
        database = source / "pastport_matching.sqlite3"
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as db:
            if identity_hash(db) != binding.identity_sha256:
                raise ValueError("Shared object identities changed")
        return database

    @contextmanager
    def spatial_connection(self) -> Iterator[sqlite3.Connection]:
        """Shadow frozen semantic tables with live authority views on each connection."""
        with closing(sqlite3.connect(self.root / "pastport_matching.sqlite3", timeout=5)) as db:
            authority = self.database
            if authority != self.root / "pastport_matching.sqlite3":
                db.execute("ATTACH DATABASE ? AS authority", (str(authority),))
                for table in CONTENT_TABLES:
                    db.execute(f'CREATE TEMP VIEW "{table}" AS SELECT * FROM authority."{table}"')
            yield db

    def bind(self, source: Path) -> None:
        """Import only provable descendants; block divergent edits without overwrites."""
        source = source.resolve()
        authority = SharedContentAuthority(source).database
        source = authority.parent
        if source == self.root:
            raise ValueError("A derived result cannot be its own content authority")
        fingerprint = digest(source / "import-manifest.json")
        if fingerprint != digest(self.root / "import-manifest.json"):
            raise ValueError("Cannot share content across different input environments")
        with closing(sqlite3.connect(authority, timeout=5)) as canonical:
            canonical.execute("BEGIN IMMEDIATE")
            with closing(
                sqlite3.connect(self.root / "pastport_matching.sqlite3", timeout=5)
            ) as local:
                local.execute("BEGIN IMMEDIATE")
                identity = identity_hash(canonical)
                if identity != identity_hash(local):
                    raise ValueError("Object stable identities differ")
                scope = hashlib.sha256((str(source) + fingerprint).encode()).hexdigest()
                binding = ContentBinding(
                    source_root=str(source),
                    import_sha256=fingerprint,
                    identity_sha256=identity,
                    scope=scope,
                )
                if self.path.is_file():
                    if ContentBinding.model_validate_json(self.path.read_bytes()) != binding:
                        raise ValueError("Shared content scope cannot change")
                    return
                self._merge(canonical, local)
                canonical.commit()
                # Legacy databases remain intact as audit/recovery snapshots.
                atomic_write(self.path, binding.model_dump_json())

    @staticmethod
    def _merge(canonical: sqlite3.Connection, local: sqlite3.Connection) -> None:
        plans: list[tuple[str, int, tuple[object, ...], list[tuple[object, ...]]]] = []
        specs = (
            (
                "content",
                "vr_display_contents",
                "object_id",
                "vr_content_events",
                "object_id",
                "historical_id,content,version,updated_at,editor,ai_draft,human_override",
                "old_content,new_content,previous_version,editor,created_at,event_type",
                2,
            ),
            (
                "review",
                "pairings",
                "modern_id",
                "review_events",
                "modern_id",
                "historical_id,image_review,text_review,version",
                "image_verdict,text_verdict,note,reviewer,created_at,previous_version",
                3,
            ),
        )
        # Immutable evidence changes cannot be discarded while consolidating copy edits.
        immutable = set(CONTENT_TABLES) - {
            "pairings",
            "vr_display_contents",
            "vr_content_events",
            "review_events",
        }
        for table in sorted(immutable):
            a = sorted(canonical.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr)
            b = sorted(local.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr)
            if a != b:
                raise SharedContentConflict(
                    f"Evidence or identity conflict in {table}; copies retained"
                )
        for kind, table, key, events, event_key, fields, event_fields, version_index in specs:
            current = {
                int(row[0]): tuple(row[1:])
                for row in canonical.execute(f"SELECT {key},{fields} FROM {table}")
            }
            copied = {
                int(row[0]): tuple(row[1:])
                for row in local.execute(f"SELECT {key},{fields} FROM {table}")
            }
            if current.keys() != copied.keys():
                raise SharedContentConflict(f"Shared {kind} object coverage changed")
            for oid, row in copied.items():
                parent = current[oid]
                if row[0] != parent[0]:
                    raise SharedContentConflict(f"Historical binding conflict for object {oid}")
                a = [
                    tuple(r)
                    for r in canonical.execute(
                        f"SELECT {event_fields} FROM {events} WHERE {event_key}=? ORDER BY id",
                        (oid,),
                    )
                ]
                b = [
                    tuple(r)
                    for r in local.execute(
                        f"SELECT {event_fields} FROM {events} WHERE {event_key}=? ORDER BY id",
                        (oid,),
                    )
                ]
                if a == b and row == parent:
                    continue
                # A preserved prefix plus one event for every version proves ancestry.
                av, bv = int(parent[version_index]), int(row[version_index])
                previous_index = 2 if kind == "content" else 5
                valid = all(int(event[previous_index]) == i for i, event in enumerate(a))
                valid = valid and all(int(event[previous_index]) == i for i, event in enumerate(b))
                if valid and av == len(a) and bv == len(b):
                    if len(a) > len(b) and a[: len(b)] == b:
                        continue
                    if len(b) > len(a) and b[: len(a)] == a:
                        if kind == "content":
                            prior = parent[5] if b[len(a)][5] == "ai_draft" else parent[1]
                            if b[len(a)][0] != prior:
                                raise SharedContentConflict(
                                    f"Content ancestry changed for object {oid}"
                                )
                        plans.append((kind, oid, row, b[len(a) :]))
                        continue
                raise SharedContentConflict(
                    f"Conflicting {kind} edits for object {oid}; both copies retained, no overwrite"
                )
        for kind, oid, row, events_to_add in plans:
            spec = next(spec for spec in specs if spec[0] == kind)
            _, table, key, event_table, event_key, fields, event_fields, _ = spec
            assignments = ",".join(f"{field}=?" for field in fields.split(","))
            canonical.execute(f"UPDATE {table} SET {assignments} WHERE {key}=?", (*row, oid))
            columns = event_fields.split(",")
            marks = ",".join("?" for _ in range(len(columns) + 1))
            for event in events_to_add:
                canonical.execute(
                    f"INSERT INTO {event_table}({event_key},{event_fields}) VALUES({marks})",
                    (oid, *event),
                )

    def snapshot_content(self, database: Path) -> None:
        """Update only a temporary export snapshot, never the frozen scene database."""
        authority = self.database
        if authority == self.root / "pastport_matching.sqlite3":
            return
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("ATTACH DATABASE ? AS authority", (str(authority),))
            db.execute("BEGIN IMMEDIATE")
            for table in CONTENT_TABLES:
                db.execute(f'DELETE FROM main."{table}"')
                db.execute(f'INSERT INTO main."{table}" SELECT * FROM authority."{table}"')
