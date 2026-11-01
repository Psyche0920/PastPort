"""Versioned VR popup copy shared by the local viewer and editorial workbench."""
from __future__ import annotations
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextlib import closing


@dataclass(frozen=True)
class VRContentDraft:
    object_id: int
    historical_id: Optional[str]
    expected_version: int
    content: str
    producer: str

    def __post_init__(self) -> None:
        if type(self.object_id) is not int or self.object_id < 1:
            raise ValueError('Invalid object identity')
        if type(self.expected_version) is not int or self.expected_version < 0:
            raise ValueError('Invalid version')
        if self.historical_id is not None and not self.historical_id.strip():
            raise ValueError('Invalid historical identity')
        if not self.content.strip() or len(self.content) > 1500:
            raise ValueError('Content must contain 1–1500 characters')
        if not self.producer.strip() or len(self.producer) > 100:
            raise ValueError('Producer required')

@dataclass(frozen=True)
class VRContentEdit:
    object_id: int
    expected_version: int
    content: str
    editor: str

    @classmethod
    def parse(cls, payload: object) -> VRContentEdit:
        if not isinstance(payload,dict):
            raise ValueError('Expected object')
        oid,version=payload.get('object_id'),payload.get('version')
        content,editor=payload.get('content'),payload.get('editor')
        if type(oid) is not int or type(version) is not int or version<0:
            raise ValueError('Invalid identity or version')
        if not isinstance(content,str) or not content.strip() or len(content)>1500:
            raise ValueError('Content must contain 1–1500 characters')
        if not isinstance(editor,str) or not editor.strip() or len(editor)>100:
            raise ValueError('Editor required')
        return cls(oid,version,content,editor.strip())

@dataclass(frozen=True)
class VRContent:
    object_id: int
    historical_id: Optional[str]
    content: str
    version: int
    updated_at: str
    editor: str
    display_source: str

    def json(self) -> str:
        return json.dumps({'object_id':self.object_id,'historical_id':self.historical_id,'content':self.content,'version':self.version,'updated_at':self.updated_at,'editor':self.editor,'display_source':self.display_source},ensure_ascii=False)

class VRContentService:
    def __init__(self, database: Path) -> None:
        self.database=database

    def initialize(self) -> None:
        with closing(sqlite3.connect(f"{self.database.resolve().as_uri()}?mode=rw", uri=True)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE IF NOT EXISTS vr_display_contents(object_id INTEGER PRIMARY KEY REFERENCES modern_objects(id),historical_id TEXT REFERENCES historical_objects(id),content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 1500),version INTEGER NOT NULL,updated_at TEXT NOT NULL,editor TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS vr_content_events(id INTEGER PRIMARY KEY,object_id INTEGER NOT NULL REFERENCES vr_display_contents(object_id),old_content TEXT NOT NULL,new_content TEXT NOT NULL,previous_version INTEGER NOT NULL,editor TEXT NOT NULL,created_at TEXT NOT NULL)')
            event_columns={row[1] for row in db.execute('PRAGMA table_info(vr_content_events)')}
            if 'event_type' not in event_columns:
                db.execute("ALTER TABLE vr_content_events ADD COLUMN event_type TEXT NOT NULL DEFAULT 'human_edit'")
            columns={row[1] for row in db.execute('PRAGMA table_info(vr_display_contents)')}
            if 'ai_draft' not in columns:
                db.execute("ALTER TABLE vr_display_contents ADD COLUMN ai_draft TEXT NOT NULL DEFAULT ''")
                db.execute('ALTER TABLE vr_display_contents ADD COLUMN human_override TEXT')
                db.execute("UPDATE vr_display_contents SET ai_draft=content,human_override=CASE WHEN editor='initial_trial_snapshot' THEN NULL ELSE content END")
            html=(self.database.parent/'vr_trial/index.html').read_text()
            match=re.search(r'<script id="tour-data" type="application/json">(.*?)</script>',html,re.S)
            if match is None:
                raise ValueError('No trial data')
            data=json.loads(match.group(1))
            for scene in data['scenes']:
                for hotspot in scene['hotspots']:
                    if not hotspot['id'].startswith('trial-object-'):
                        continue
                    oid=int(hotspot['id'].removeprefix('trial-object-'))
                    source=db.execute('SELECT historical_id FROM pairings WHERE modern_id=?',(oid,)).fetchone()[0]
                    db.execute('INSERT OR IGNORE INTO vr_display_contents(object_id,historical_id,content,version,updated_at,editor,ai_draft,human_override) VALUES (?,?,?,?,?,?,?,NULL)',(oid,source,hotspot['text'],0,datetime.now(timezone.utc).isoformat(),'initial_trial_snapshot',hotspot['text']))
            db.commit()

    def read(self, object_id: int) -> Optional[VRContent]:
        with closing(sqlite3.connect(f"{self.database.resolve().as_uri()}?mode=rw", uri=True)) as db:
            row=db.execute("SELECT v.object_id,v.historical_id,COALESCE(v.human_override,v.ai_draft),v.version,v.updated_at,v.editor,CASE WHEN v.human_override IS NULL THEN 'ai_draft' ELSE 'human_override' END FROM vr_display_contents v JOIN pairings p ON p.modern_id=v.object_id WHERE v.object_id=? AND v.historical_id IS p.historical_id AND p.image_review != 'unsuitable' AND p.text_review != 'unsuitable' AND p.proposal_state != \'invalid_structural_relation\'",(object_id,)).fetchone()
            return VRContent(*row) if row else None

    def save_draft(self, draft: VRContentDraft) -> bool:
        """Keep generated copy separate from the human override and reject stale work."""
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT ai_draft FROM vr_display_contents WHERE object_id=? AND version=?',(draft.object_id,draft.expected_version)).fetchone()
            if old is None:
                return False
            stamp=datetime.now(timezone.utc).isoformat()
            count=db.execute(
                'UPDATE vr_display_contents SET ai_draft=?,content=COALESCE(human_override,?),version=version+1,updated_at=?,editor=CASE WHEN human_override IS NULL THEN ? ELSE editor END WHERE object_id=? AND version=? AND historical_id IS ? AND EXISTS (SELECT 1 FROM pairings p WHERE p.modern_id=vr_display_contents.object_id AND p.historical_id IS vr_display_contents.historical_id AND p.proposal_state != \'invalid_structural_relation\')',
                (draft.content,draft.content,stamp,draft.producer,draft.object_id,draft.expected_version,draft.historical_id),
            ).rowcount
            if count != 1:
                return False
            db.execute(
                "INSERT INTO vr_content_events(object_id,old_content,new_content,previous_version,editor,created_at,event_type) VALUES (?,?,?,?,?,?,'ai_draft')",
                (draft.object_id,old[0],draft.content,draft.expected_version,draft.producer,stamp),
            )
            return True

    def save(self, edit: VRContentEdit) -> bool:
        connection=sqlite3.connect(f"{self.database.resolve().as_uri()}?mode=rw", uri=True,timeout=5)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                old=connection.execute('SELECT content FROM vr_display_contents WHERE object_id=? AND version=?',(edit.object_id,edit.expected_version)).fetchone()
                if old is None:
                    return False
                stamp=datetime.now(timezone.utc).isoformat()
                count=connection.execute('UPDATE vr_display_contents SET content=?,human_override=?,version=version+1,updated_at=?,editor=? WHERE object_id=? AND version=? AND historical_id IS (SELECT historical_id FROM pairings WHERE modern_id=? AND proposal_state != \'invalid_structural_relation\')',(edit.content,edit.content,stamp,edit.editor,edit.object_id,edit.expected_version,edit.object_id)).rowcount
                if count!=1:
                    return False
                connection.execute('INSERT INTO vr_content_events(object_id,old_content,new_content,previous_version,editor,created_at) VALUES (?,?,?,?,?,?)',(edit.object_id,old[0],edit.content,edit.expected_version,edit.editor,stamp))
                return True
        finally:
            connection.close()
