"""Seed 3D navigation once from VR; all later spatial edits stay local to this result."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from pastport_matched_environment.application.reference_environment import read_json, record, string
from pastport_matched_environment.domain.scene3d import (
    Scene3DArrow,
    Scene3DArrowEdit,
    Scene3DArrowSet,
    Scene3DNavigation,
)


class Scene3DArrowStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.database = root / "pastport_matching.sqlite3"
        attachment = record(read_json(root / "scene3d/attachment.json"))
        self.binding = string(attachment["binding"])
        self.source_scene = string(attachment["source_scene_id"])
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scene3d_arrows(binding TEXT NOT NULL,
                    hotspot_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(binding,hotspot_id));
                CREATE TABLE IF NOT EXISTS scene3d_arrow_events(operation_id TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,response TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """)

    def current(self) -> Scene3DArrowSet:
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT payload FROM scene3d_arrows WHERE binding=? ORDER BY hotspot_id",
                (self.binding,),
            ).fetchall()
            if not rows:
                path = self.root / "scene3d/arrow-seed.json"
                if path.is_file():
                    if path.stat().st_size > 128 * 1024:
                        raise ValueError("Arrow seed exceeds profile")
                    seed = Scene3DNavigation.model_validate_json(path.read_bytes())
                    if seed.source_scene_id != self.source_scene:
                        raise ValueError("Arrow source scene changed")
                    if len({item.hotspot_id for item in seed.transitions}) != len(seed.transitions):
                        raise ValueError("Duplicate arrow seed")
                    for item in seed.transitions:
                        url = urlsplit(item.target_url)
                        if (
                            url.scheme != "http"
                            or url.hostname not in ("127.0.0.1", "localhost")
                            or not url.path.startswith("/scene3d-results/")
                        ):
                            raise ValueError("Invalid arrow target")
                        arrow = Scene3DArrow.model_validate(item.model_dump())
                        db.execute(
                            "INSERT OR IGNORE INTO scene3d_arrows VALUES(?,?,?)",
                            (self.binding, arrow.hotspot_id, arrow.model_dump_json()),
                        )
                    rows = db.execute(
                        "SELECT payload FROM scene3d_arrows WHERE binding=? ORDER BY hotspot_id",
                        (self.binding,),
                    ).fetchall()
        return Scene3DArrowSet(
            scene_binding=self.binding,
            source_scene_id=self.source_scene,
            arrows=tuple(Scene3DArrow.model_validate_json(row[0]) for row in rows),
        )

    def save(self, edit: Scene3DArrowEdit) -> Scene3DArrow | None:
        if edit.scene_binding != self.binding:
            raise ValueError("Arrow scene binding changed")
        digest = hashlib.sha256(edit.model_dump_json().encode()).hexdigest()
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            replay = db.execute(
                "SELECT request_hash,response FROM scene3d_arrow_events WHERE operation_id=?",
                (edit.operation_id,),
            ).fetchone()
            if replay:
                if replay[0] != digest:
                    raise ValueError("Arrow operation reused with different payload")
                return Scene3DArrow.model_validate_json(replay[1])
            row = db.execute(
                "SELECT payload FROM scene3d_arrows WHERE binding=? AND hotspot_id=?",
                (self.binding, edit.hotspot_id),
            ).fetchone()
            if row is None:
                raise ValueError("Unregistered arrow")
            current = Scene3DArrow.model_validate_json(row[0])
            if current.version != edit.expected_version:
                return None
            if edit.placement == "projected" and current.point is not None:
                return None
            saved = current.model_copy(
                update={
                    "point": edit.point,
                    "placement": edit.placement,
                    "version": current.version + 1,
                }
            )
            db.execute(
                "UPDATE scene3d_arrows SET payload=? WHERE binding=? AND hotspot_id=?",
                (saved.model_dump_json(), self.binding, edit.hotspot_id),
            )
            db.execute(
                "INSERT INTO scene3d_arrow_events(operation_id,request_hash,response) "
                "VALUES(?,?,?)",
                (edit.operation_id, digest, saved.model_dump_json()),
            )
            return saved
