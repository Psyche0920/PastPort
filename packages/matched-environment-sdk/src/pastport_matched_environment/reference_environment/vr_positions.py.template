"""Persist scene-specific human hotspot corrections independently of model output."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PositionKey:
    object_id: int
    scene_id: str
    panorama_revision: int
    panorama_sha256: str

    def values(self) -> tuple[int, str, int, str]:
        return (self.object_id, self.scene_id, self.panorama_revision, self.panorama_sha256)


@dataclass(frozen=True)
class Position:
    key: PositionKey
    yaw: float
    pitch: float
    version: int
    source: str


@dataclass(frozen=True)
class PositionEdit:
    key: PositionKey
    yaw: float
    pitch: float
    version: int
    operation_id: str

    @classmethod
    def parse(cls, value: object) -> PositionEdit:
        if not isinstance(value, dict):
            raise ValueError('Expected an object')
        oid, scene, revision, digest = (value.get(k) for k in (
            'object_id', 'scene_id', 'panorama_revision', 'panorama_sha256'))
        yaw, pitch, version, operation = (value.get(k) for k in (
            'yaw', 'pitch', 'version', 'operation_id'))
        if type(oid) is not int or oid < 1 or not isinstance(scene, str) or not 1 <= len(scene) <= 100:
            raise ValueError('Invalid object or scene')
        if type(revision) is not int or revision < 1 or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Invalid panorama revision')
        if type(version) is not int or version < 0:
            raise ValueError('Invalid version')
        if not isinstance(operation, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', operation):
            raise ValueError('Invalid operation ID')
        if isinstance(yaw, bool) or not isinstance(yaw, (int, float)) or isinstance(pitch, bool) or not isinstance(pitch, (int, float)):
            raise ValueError('Invalid coordinates')
        if not math.isfinite(yaw) or not math.isfinite(pitch) or not -180 <= yaw <= 180 or not -90 <= pitch <= 90:
            raise ValueError('Coordinates outside spherical range')
        return cls(PositionKey(oid, scene, revision, digest), float(yaw), float(pitch), version, operation)


class VRPositionService:
    def __init__(self, database: Path, manifest: Path) -> None:
        self.database = database
        self.manifest = manifest

    def proposals(self) -> tuple[Position, ...]:
        if self.manifest.stat().st_size > 2_000_000:
            raise ValueError('Position manifest too large')
        payload: object = json.loads(self.manifest.read_text())
        if not isinstance(payload, dict) or not isinstance(payload.get('located'), list):
            raise ValueError('Invalid position manifest')
        positions: list[Position] = []
        for row in payload['located']:
            if not isinstance(row, dict):
                raise ValueError('Invalid position proposal')
            edit = PositionEdit.parse({**row, 'version': 0, 'operation_id': 'manifest-proposal'})
            positions.append(Position(edit.key, edit.yaw, edit.pitch, 0, 'model_proposal'))
        if len({p.key for p in positions}) != len(positions):
            raise ValueError('Duplicate object/scene proposal')
        return tuple(positions)

    def initialize(self) -> None:
        proposals = self.proposals()
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('''CREATE TABLE IF NOT EXISTS vr_positions(
                object_id INTEGER NOT NULL REFERENCES modern_objects(id), scene_id TEXT NOT NULL,
                panorama_revision INTEGER NOT NULL, panorama_sha256 TEXT NOT NULL,
                model_yaw REAL NOT NULL, model_pitch REAL NOT NULL,
                human_yaw REAL, human_pitch REAL, version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT, editor TEXT,
                PRIMARY KEY(object_id,scene_id,panorama_revision,panorama_sha256))''')
            db.execute('''CREATE TABLE IF NOT EXISTS vr_position_events(
                operation_id TEXT PRIMARY KEY, object_id INTEGER NOT NULL, scene_id TEXT NOT NULL,
                panorama_revision INTEGER NOT NULL, panorama_sha256 TEXT NOT NULL,
                old_yaw REAL NOT NULL, old_pitch REAL NOT NULL, new_yaw REAL NOT NULL,
                new_pitch REAL NOT NULL, previous_version INTEGER NOT NULL,
                editor TEXT NOT NULL, created_at TEXT NOT NULL)''')
            for p in proposals:
                db.execute('''INSERT INTO vr_positions(
                    object_id,scene_id,panorama_revision,panorama_sha256,model_yaw,model_pitch)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(object_id,scene_id,panorama_revision,panorama_sha256)
                    DO UPDATE SET model_yaw=excluded.model_yaw,model_pitch=excluded.model_pitch,
                    version=vr_positions.version+1
                    WHERE model_yaw!=excluded.model_yaw OR model_pitch!=excluded.model_pitch''',
                    (*p.key.values(), p.yaw, p.pitch))

    @staticmethod
    def _read(db: sqlite3.Connection, key: PositionKey) -> Optional[Position]:
        row = db.execute('''SELECT COALESCE(human_yaw,model_yaw),COALESCE(human_pitch,model_pitch),
            version,CASE WHEN human_yaw IS NULL THEN 'model_proposal' ELSE 'human_override' END
            FROM vr_positions WHERE object_id=? AND scene_id=? AND panorama_revision=? AND panorama_sha256=?''',
            key.values()).fetchone()
        return Position(key, float(row[0]), float(row[1]), int(row[2]), str(row[3])) if row else None

    def current(self) -> tuple[Position, ...]:
        proposals = self.proposals()
        with closing(sqlite3.connect(self.database, timeout=5)) as db:
            return tuple(self._read(db, p.key) or p for p in proposals)

    def save(self, edit: PositionEdit) -> Optional[Position]:
        if edit.key not in {p.key for p in self.proposals()}:
            return None
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = self._read(db, edit.key)
            if old is None:
                return None
            prior = db.execute('''SELECT object_id,scene_id,panorama_revision,panorama_sha256,new_yaw,new_pitch
                FROM vr_position_events WHERE operation_id=?''', (edit.operation_id,)).fetchone()
            if prior is not None:
                if tuple(prior) != (*edit.key.values(), edit.yaw, edit.pitch):
                    raise ValueError('Operation ID reused with different payload')
                return old
            if old.version != edit.version:
                return None
            stamp = datetime.now(timezone.utc).isoformat()
            db.execute('''UPDATE vr_positions SET human_yaw=?,human_pitch=?,version=version+1,
                updated_at=?,editor='local_reviewer' WHERE object_id=? AND scene_id=?
                AND panorama_revision=? AND panorama_sha256=? AND version=?''',
                (edit.yaw, edit.pitch, stamp, *edit.key.values(), edit.version))
            db.execute('''INSERT INTO vr_position_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (edit.operation_id, *edit.key.values(), old.yaw, old.pitch, edit.yaw,
                 edit.pitch, edit.version, 'local_reviewer', stamp))
            return self._read(db, edit.key)

    @staticmethod
    def encode(positions: tuple[Position, ...]) -> str:
        return json.dumps([asdict(p) for p in positions], ensure_ascii=False)
