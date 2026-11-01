"""Canonical existing review persistence, shared by the viewer and Organizer."""
from __future__ import annotations
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

@dataclass(frozen=True)
class Review:
    object_id: int
    version: int
    image: str
    text: str
    note: str
    reviewer: str

    @classmethod
    def parse(cls, value: object) -> Review:
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        image, text = value.get('image'), value.get('text')
        if image not in ('unreviewed','suitable','unsuitable','uncertain') or text not in ('unreviewed','direct','context_only','unsuitable','uncertain'):
            raise ValueError('Invalid verdict')
        oid, version = value.get('object_id'), value.get('version')
        note, reviewer = value.get('note'), value.get('reviewer')
        if type(oid) is not int or type(version) is not int or not isinstance(note,str) or not isinstance(reviewer,str):
            raise ValueError('Invalid review fields')
        if not reviewer.strip() or len(note)>4000 or len(reviewer)>100:
            raise ValueError('Reviewer required; note limited to 4000 characters')
        return cls(oid,version,image,text,note,reviewer.strip())

class ReviewRepository:
    def __init__(self, database: Path) -> None:
        self.database = database

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(f"{self.database.resolve().as_uri()}?mode=rw", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def dataset(self) -> str:
        with self.connection() as db:
            objects = [dict(row) for row in db.execute('SELECT m.*,p.historical_id,p.proposal_state,p.rationale,p.image_review,p.text_review,p.version FROM modern_objects m JOIN pairings p ON m.id=p.modern_id ORDER BY m.id')]
            sources = [dict(row) for row in db.execute('SELECT h.*,a.verdict AS audit_verdict,a.recommended_display_zh,a.limitation AS audit_limitation,t.translation_zh,p.exact_text,p.pdf_page AS text_page,NULLIF(s.printed_page,0) AS text_printed_page,p.start_offset,p.end_offset,s.normalized_text AS page_context FROM historical_objects h LEFT JOIN assistant_semantic_audit a ON a.historical_id=h.id LEFT JOIN text_associations t ON t.historical_id=h.id LEFT JOIN passages p ON p.id=t.passage_id LEFT JOIN source_pages s ON s.pdf_page=p.pdf_page')]
            result = {'objects':objects,'sources':sources,'photos':[dict(r) for r in db.execute('SELECT * FROM photos')], 'observations':[dict(r) for r in db.execute('SELECT * FROM observations')], 'reviews':[dict(r) for r in db.execute('SELECT * FROM review_events ORDER BY id')], 'references':[dict(r) for r in db.execute('SELECT * FROM design_references')], 'vr_contents':[dict(r) for r in db.execute("SELECT v.*,CASE WHEN v.human_override IS NULL THEN 'ai_draft' ELSE 'human_override' END AS display_source,(p.historical_id IS v.historical_id AND p.proposal_state != 'invalid_structural_relation') AS mapping_current FROM vr_display_contents v JOIN pairings p ON p.modern_id=v.object_id")]}
            return json.dumps(result,ensure_ascii=False)

    def save(self, review: Review) -> bool:
        with self.connection() as db:
            changed = db.execute('UPDATE pairings SET image_review=?,text_review=?,version=version+1 WHERE modern_id=? AND version=?',(review.image,review.text,review.object_id,review.version)).rowcount
            if not changed:
                return False
            db.execute('INSERT INTO review_events(modern_id,image_verdict,text_verdict,note,reviewer,created_at,previous_version) VALUES (?,?,?,?,?,?,?)',(review.object_id,review.image,review.text,review.note,review.reviewer,datetime.now(timezone.utc).isoformat(),review.version))
            return True
