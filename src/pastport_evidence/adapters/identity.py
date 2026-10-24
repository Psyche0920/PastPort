"""Transactional scene identity allocation without category/name-based merging."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from pastport_evidence.domain.recognition import EntityProposal, SceneEntity


class IdentityConflict(ValueError):
    """An identity alias or cached response conflicts with its immutable binding."""


class ScenePersistenceError(RuntimeError):
    """Scene records cannot be read or committed."""


class SQLiteSceneRepository:
    def __init__(self, database: Path) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self._database = database
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS scene_entities (
                    project_id TEXT NOT NULL, object_id TEXT NOT NULL,
                    display_number INTEGER NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(project_id,object_id),
                    UNIQUE(project_id,display_number));
                CREATE TABLE IF NOT EXISTS scene_aliases (
                    project_id TEXT NOT NULL, binding TEXT NOT NULL, proposal_id TEXT NOT NULL,
                    object_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    PRIMARY KEY(project_id,binding,proposal_id),
                    FOREIGN KEY(project_id,object_id)
                        REFERENCES scene_entities(project_id,object_id));
            """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database, timeout=5)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        except sqlite3.Error as error:
            raise ScenePersistenceError("Scene identity persistence operation failed") from error
        finally:
            connection.close()

    def list_entities(self, project_id: str) -> tuple[SceneEntity, ...]:
        with self._connection() as connection:
            return self._entities(connection, project_id)

    @staticmethod
    def _entities(connection: sqlite3.Connection, project_id: str) -> tuple[SceneEntity, ...]:
        rows = connection.execute(
            "SELECT payload FROM scene_entities WHERE project_id=? ORDER BY display_number",
            (project_id,),
        ).fetchall()
        try:
            return tuple(SceneEntity.model_validate_json(row[0]) for row in rows)
        except ValidationError as error:
            raise ScenePersistenceError("Stored scene entity failed schema validation") from error

    def resolve_proposals(
        self, project_id: str, binding: str, proposals: tuple[EntityProposal, ...]
    ) -> dict[str, SceneEntity]:
        if len({p.proposal_id for p in proposals}) != len(proposals):
            raise IdentityConflict("Duplicate run-local proposal identity")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            known = {e.object_id: e for e in self._entities(connection, project_id)}
            next_number = max((e.display_number for e in known.values()), default=0) + 1
            resolved: dict[str, SceneEntity] = {}
            pending: list[tuple[EntityProposal, str, str]] = []
            for proposal in proposals:
                fingerprint = hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()
                alias = connection.execute(
                    "SELECT object_id,fingerprint FROM scene_aliases "
                    "WHERE project_id=? AND binding=? AND proposal_id=?",
                    (project_id, binding, proposal.proposal_id),
                ).fetchone()
                if alias:
                    if alias[1] != fingerprint:
                        raise IdentityConflict("Proposal changed under an existing input binding")
                    resolved[proposal.proposal_id] = known[alias[0]]
                    continue
                if proposal.existing_object_id:
                    if proposal.existing_object_id not in known:
                        raise IdentityConflict(
                            "Cross-view identity references an unknown project entity"
                        )
                    entity = known[proposal.existing_object_id]
                else:
                    entity = SceneEntity(
                        object_id="object:" + uuid4().hex,
                        display_number=next_number,
                        label=proposal.label,
                        category=proposal.category,
                        distinguishing_features=proposal.distinguishing_features,
                    )
                    next_number += 1
                    known[entity.object_id] = entity
                resolved[proposal.proposal_id] = entity
                pending.append((proposal, entity.object_id, fingerprint))
            ids = [entity.object_id for entity in resolved.values()]
            if len(ids) != len(set(ids)):
                raise IdentityConflict("Multiple proposals cannot implicitly merge into one entity")
            for proposal, object_id, fingerprint in pending:
                entity = resolved[proposal.proposal_id]
                if proposal.parent_ref:
                    parent = resolved.get(proposal.parent_ref) or known.get(proposal.parent_ref)
                    if parent is None or parent.object_id == object_id:
                        raise IdentityConflict("Unknown or self-referencing parent identity")
                    if proposal.existing_object_id and entity.parent_object_id != parent.object_id:
                        raise IdentityConflict(
                            "Model cannot rewrite an existing containment decision"
                        )
                    entity = entity.model_copy(update={"parent_object_id": parent.object_id})
                    resolved[proposal.proposal_id] = entity
                    known[object_id] = entity
                connection.execute(
                    "INSERT OR IGNORE INTO scene_entities VALUES (?,?,?,?)",
                    (project_id, object_id, entity.display_number, entity.model_dump_json()),
                )
                connection.execute(
                    "INSERT INTO scene_aliases VALUES (?,?,?,?,?)",
                    (project_id, binding, proposal.proposal_id, object_id, fingerprint),
                )
            for entity in known.values():
                seen: set[str] = set()
                current: SceneEntity | None = entity
                while current:
                    if current.object_id in seen:
                        raise IdentityConflict("Containment graph contains a cycle")
                    seen.add(current.object_id)
                    current = (
                        known.get(current.parent_object_id) if current.parent_object_id else None
                    )
            return resolved
