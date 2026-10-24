"""Transactional local review storage with CAS, idempotency and immutable event history."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pastport_pdf_vr.domain.editorial import (
    EditResult,
    EffectiveAnchor,
    EffectiveObject,
    PositionEdit,
    PreviewAnchor,
    PreviewObject,
    PreviewSnapshot,
    TextEdit,
)
from pastport_pdf_vr.domain.evidence import DisplayCopy
from pastport_pdf_vr.domain.geometry import AnchorPosition


class EditConflict(ValueError):
    """An edit is stale, bound to another assignment/media revision or reuses an operation ID."""


class EditorialError(RuntimeError):
    """Editorial state cannot be safely read or saved."""


class SQLiteEditorialRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS preview_projects (
                    project TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    input_binding TEXT NOT NULL, mode TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preview_objects (
                    project TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,
                    PRIMARY KEY(project,id));
                CREATE TABLE IF NOT EXISTS preview_anchors (
                    project TEXT NOT NULL,id TEXT NOT NULL,view_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(project,id,view_id));
                CREATE TABLE IF NOT EXISTS human_overrides (
                    project TEXT NOT NULL,kind TEXT NOT NULL,scope TEXT NOT NULL,
                    version INTEGER NOT NULL,payload TEXT NOT NULL,
                    PRIMARY KEY(project,kind,scope));
                CREATE TABLE IF NOT EXISTS editorial_events (
                    project TEXT NOT NULL,operation TEXT NOT NULL,fingerprint TEXT NOT NULL,
                    result TEXT NOT NULL,payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(project,operation));
            """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._path, timeout=5)
        try:
            with db:
                yield db
        except sqlite3.Error as error:
            raise EditorialError("Editorial database operation failed") from error
        finally:
            db.close()

    def publish_proposals(
        self,
        project: str,
        binding: str,
        mode: Literal["synthetic_replay", "model_generated"],
        objects: tuple[PreviewObject, ...],
        anchors: tuple[PreviewAnchor, ...],
    ) -> int:
        ids = {obj.entity.object_id for obj in objects}
        if len(ids) != len(objects) or len({obj.entity.display_number for obj in objects}) != len(
            objects
        ):
            raise EditorialError("Preview object identities and display numbers must be unique")
        keys = {(anchor.object_id, anchor.view_id) for anchor in anchors}
        if len(keys) != len(anchors) or any(
            anchor.object_id not in ids or anchor.panorama.project_id != project
            for anchor in anchors
        ):
            raise EditorialError("Preview anchor references are invalid")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision,input_binding,mode FROM preview_projects WHERE project=?",
                (project,),
            ).fetchone()
            if row and row[1:] == (binding, mode):
                old_objects = tuple(
                    r[0]
                    for r in db.execute(
                        "SELECT payload FROM preview_objects WHERE project=? ORDER BY id",
                        (project,),
                    )
                )
                old_anchors = tuple(
                    r[0]
                    for r in db.execute(
                        "SELECT payload FROM preview_anchors WHERE project=? ORDER BY id,view_id",
                        (project,),
                    )
                )
                if old_objects != tuple(
                    o.model_dump_json() for o in sorted(objects, key=lambda o: o.entity.object_id)
                ) or old_anchors != tuple(
                    a.model_dump_json()
                    for a in sorted(anchors, key=lambda a: (a.object_id, a.view_id))
                ):
                    raise EditConflict("Proposal payload changed under the same immutable binding")
                return int(row[0])
            revision = int(row[0]) + 1 if row else 1
            # Only model proposal tables are replaced. Human values/events remain separate.
            db.execute("DELETE FROM preview_objects WHERE project=?", (project,))
            db.execute("DELETE FROM preview_anchors WHERE project=?", (project,))
            db.executemany(
                "INSERT INTO preview_objects VALUES (?,?,?)",
                ((project, o.entity.object_id, o.model_dump_json()) for o in objects),
            )
            db.executemany(
                "INSERT INTO preview_anchors VALUES (?,?,?,?)",
                ((project, a.object_id, a.view_id, a.model_dump_json()) for a in anchors),
            )
            db.execute(
                "INSERT INTO preview_projects VALUES (?,?,?,?) ON CONFLICT(project) "
                "DO UPDATE SET "
                "revision=excluded.revision,input_binding=excluded.input_binding,mode=excluded.mode",
                (project, revision, binding, mode),
            )
            return revision

    def save_text(self, project: str, edit: TextEdit) -> EditResult:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._replayed(db, project, edit.operation_id, edit.model_dump_json())
            if previous:
                return previous
            row = db.execute(
                "SELECT payload FROM preview_objects WHERE project=? AND id=?",
                (project, edit.object_id),
            ).fetchone()
            if row is None:
                raise EditConflict("Unknown project object")
            obj = PreviewObject.model_validate_json(row[0])
            if obj.historical_subject_id != edit.historical_subject_id:
                raise EditConflict("Historical assignment changed; revalidate text before saving")
            scope = f"{edit.object_id}|{edit.historical_subject_id}"
            value = DisplayCopy(
                subject_id=edit.historical_subject_id,
                version=edit.expected_version + 1,
                introduction=edit.introduction,
                background=edit.background,
            )
            return self._save(
                db,
                project,
                "text",
                scope,
                edit.expected_version,
                edit.operation_id,
                edit.model_dump_json(),
                value.model_dump_json(),
            )

    def save_position(self, project: str, edit: PositionEdit) -> EditResult:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._replayed(db, project, edit.operation_id, edit.model_dump_json())
            if previous:
                return previous
            row = db.execute(
                "SELECT payload FROM preview_anchors WHERE project=? AND id=? AND view_id=?",
                (project, edit.object_id, edit.view_id),
            ).fetchone()
            if row is None:
                raise EditConflict("Unknown project object/view anchor")
            anchor = PreviewAnchor.model_validate_json(row[0])
            if (
                anchor.panorama != edit.panorama
                or anchor.panorama_revision != edit.panorama_revision
            ):
                raise EditConflict("Panorama changed; revalidate position before saving")
            scope = self._position_scope(anchor)
            return self._save(
                db,
                project,
                "position",
                scope,
                edit.expected_version,
                edit.operation_id,
                edit.model_dump_json(),
                edit.position.model_dump_json(),
            )

    @staticmethod
    def _position_scope(anchor: PreviewAnchor) -> str:
        return hashlib.sha256(
            (
                anchor.object_id
                + "|"
                + anchor.view_id
                + "|"
                + anchor.panorama.model_dump_json()
                + "|"
                + str(anchor.panorama_revision)
            ).encode()
        ).hexdigest()

    @staticmethod
    def _replayed(
        db: sqlite3.Connection, project: str, operation: str, payload: str
    ) -> EditResult | None:
        row = db.execute(
            "SELECT fingerprint,result FROM editorial_events WHERE project=? AND operation=?",
            (project, operation),
        ).fetchone()
        if row is None:
            return None
        if row[0] != hashlib.sha256(payload.encode()).hexdigest():
            raise EditConflict("Operation ID was already used for different edit content")
        return EditResult.model_validate_json(row[1])

    def _save(
        self,
        db: sqlite3.Connection,
        project: str,
        kind: str,
        scope: str,
        expected: int,
        operation: str,
        request: str,
        payload: str,
    ) -> EditResult:
        row = db.execute(
            "SELECT version FROM human_overrides WHERE project=? AND kind=? AND scope=?",
            (project, kind, scope),
        ).fetchone()
        version = int(row[0]) if row else 0
        if version != expected:
            raise EditConflict("Newer edit exists; reload before saving")
        project_row = db.execute(
            "SELECT revision FROM preview_projects WHERE project=?", (project,)
        ).fetchone()
        if project_row is None:
            raise EditConflict("Unknown project")
        revision = int(project_row[0]) + 1
        db.execute(
            "INSERT INTO human_overrides VALUES (?,?,?,?,?) ON CONFLICT(project,kind,scope) "
            "DO UPDATE SET version=excluded.version,payload=excluded.payload",
            (project, kind, scope, version + 1, payload),
        )
        db.execute("UPDATE preview_projects SET revision=? WHERE project=?", (revision, project))
        result = EditResult(operation_id=operation, version=version + 1, project_revision=revision)
        db.execute(
            "INSERT INTO "
            "editorial_events(project,operation,fingerprint,result,payload) VALUES (?,?,?,?,?)",
            (
                project,
                operation,
                hashlib.sha256(request.encode()).hexdigest(),
                result.model_dump_json(),
                request,
            ),
        )
        return result

    def snapshot(self, project: str) -> PreviewSnapshot:
        with self._connection() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT revision,input_binding,mode FROM preview_projects WHERE project=?",
                (project,),
            ).fetchone()
            if row is None:
                raise EditorialError("Project preview has not been generated")
            objects = []
            for record in db.execute(
                "SELECT payload FROM preview_objects WHERE project=? ORDER BY id", (project,)
            ):
                obj = PreviewObject.model_validate_json(record[0])
                scope = f"{obj.entity.object_id}|{obj.historical_subject_id}"
                human = db.execute(
                    "SELECT version,payload FROM human_overrides WHERE project=? AND "
                    "kind='text' AND scope=?",
                    (project, scope),
                ).fetchone()
                if human:
                    copy = DisplayCopy.model_validate_json(human[1])
                    objects.append(
                        EffectiveObject(
                            object=obj,
                            introduction=copy.introduction,
                            background=copy.background,
                            origin="human",
                            version=int(human[0]),
                        )
                    )
                else:
                    draft = obj.draft
                    mismatch = (
                        db.execute(
                            "SELECT 1 FROM editorial_events WHERE project=? AND "
                            "json_extract(payload,'$.object_id')=? AND "
                            "json_extract(payload,'$.introduction') IS NOT NULL LIMIT 1",
                            (project, obj.entity.object_id),
                        ).fetchone()
                        is not None
                    )
                    objects.append(
                        EffectiveObject(
                            object=obj,
                            introduction=draft.introduction if draft else "",
                            background=draft.background if draft else "",
                            origin="ai" if draft else "unbound",
                            version=0,
                            assignment_mismatch=mismatch,
                        )
                    )
            anchors = []
            for record in db.execute(
                "SELECT payload FROM preview_anchors WHERE project=? ORDER BY id,view_id",
                (project,),
            ):
                anchor = PreviewAnchor.model_validate_json(record[0])
                human = db.execute(
                    "SELECT version,payload FROM human_overrides WHERE project=? AND "
                    "kind='position' AND scope=?",
                    (project, self._position_scope(anchor)),
                ).fetchone()
                anchors.append(
                    EffectiveAnchor(
                        anchor=anchor,
                        position=AnchorPosition.model_validate_json(human[1])
                        if human
                        else anchor.position,
                        origin="human" if human else "model",
                        version=int(human[0]) if human else 0,
                    )
                )
            return PreviewSnapshot.model_validate(
                {
                    "project_id": project,
                    "revision": row[0],
                    "input_binding": row[1],
                    "mode": row[2],
                    "objects": tuple(objects),
                    "anchors": tuple(anchors),
                }
            )
