"""Validate and import the versioned photographic chapter into SQLite."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple, cast


class StoryImportError(ValueError):
    """Raised when narrative references cannot be supported by the catalogue."""


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise StoryImportError('Expected a JSON object.')
    return cast(Mapping[str, object], value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise StoryImportError('Expected a non-empty string.')
    return value


def _list(value: object) -> Tuple[object, ...]:
    if not isinstance(value, list):
        raise StoryImportError('Expected a JSON array.')
    return tuple(value)


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StoryImportError('Expected an integer.')
    return value


@dataclass(frozen=True)
class PhotoRecord:
    photo_id: str
    source_id: str
    file_path: str
    pdf_page: int
    printed_page: str
    image_index: int
    caption: str
    structure_id: str | None

    @classmethod
    def parse(cls, value: object) -> PhotoRecord:
        row = _mapping(value)
        structure = row.get('structure_id')
        return cls(_text(row.get('id')), _text(row.get('source_id')),
                   _text(row.get('file')), _integer(row.get('pdf_page')),
                   _text(row.get('printed_page')), _integer(row.get('image_index')),
                   _text(row.get('caption')), None if structure is None else _text(structure))


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    prompt: str
    options_json: str
    effects_json: str

    @classmethod
    def parse(cls, value: object) -> DecisionRecord:
        row = _mapping(value)
        options = _list(row.get('options'))
        effects = {_text(_mapping(option).get('id')): _mapping(option).get('effects') for option in options}
        return cls(_text(row.get('id')), _text(row.get('prompt')),
                   json.dumps(options, ensure_ascii=False), json.dumps(effects, ensure_ascii=False))


@dataclass(frozen=True)
class SceneRecord:
    scene_id: str
    title: str
    photo_id: str
    claim_ids: Tuple[str, ...]
    task_json: str
    decision: DecisionRecord | None

    @classmethod
    def parse(cls, value: object) -> SceneRecord:
        row = _mapping(value)
        decision = row.get('decision')
        return cls(_text(row.get('id')), _text(row.get('title')), _text(row.get('photo_id')),
                   tuple(_text(item) for item in _list(row.get('claim_ids'))),
                   json.dumps(_mapping(row.get('task')), ensure_ascii=False),
                   None if decision is None else DecisionRecord.parse(decision))


@dataclass(frozen=True)
class ChapterRecord:
    chapter_id: str
    version: str
    title: str
    period: str
    notice: str
    payload_json: str
    content_sha256: str
    photos: Tuple[PhotoRecord, ...]
    scenes: Tuple[SceneRecord, ...]

    @classmethod
    def read(cls, path: Path) -> ChapterRecord:
        try:
            text = path.read_text(encoding='utf-8')
            row = _mapping(json.loads(text))
        except (OSError, json.JSONDecodeError) as error:
            raise StoryImportError(f'Cannot read chapter: {error}') from error
        return cls(_text(row.get('chapter_id')), _text(row.get('version')), _text(row.get('title')),
                   _text(row.get('period')), _text(row.get('fiction_notice')), text,
                   hashlib.sha256(text.encode()).hexdigest(),
                   tuple(PhotoRecord.parse(photo) for photo in _list(row.get('photos'))),
                   tuple(SceneRecord.parse(scene) for scene in _list(row.get('scenes'))))


class NarrativeImporter:
    """Persist the same chapter file consumed by the browser, with source checks."""
    NODE_IDS = {'arrival':'node-overview', 'courtyard':'node-medrese', 'fountain':'node-fountain',
                'imaret':'node-imaret', 'reckoning':'node-mosque'}
    SLOT_IDS = {'arrival':'slot-overview-map', 'courtyard':'slot-medrese-observation',
                'fountain':'slot-fountain-duty', 'imaret':'slot-imaret-flow', 'reckoning':'slot-report-choice'}

    def import_chapter(self, connection: sqlite3.Connection, record: ChapterRecord, project_root: Path) -> None:
        self._validate(connection, record, project_root)
        connection.execute('''INSERT INTO narrative_versions
            (chapter_id, version, content_sha256, payload_json) VALUES (?, ?, ?, ?)''',
            (record.chapter_id, record.version, record.content_sha256, record.payload_json))
        connection.executemany('''INSERT INTO media_derivatives
            (derivative_id, source_id, local_path, pdf_page, printed_page, image_index, caption, structure_id, review_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'verified')''',
            [(photo.photo_id, photo.source_id, 'prototype/' + photo.file_path, photo.pdf_page,
              photo.printed_page, photo.image_index, photo.caption, photo.structure_id) for photo in record.photos])
        connection.execute('UPDATE chapters SET title = ?, period_text = ?, premise = ?, fiction_notice = ? WHERE chapter_id = ?',
                           (record.title, record.period, 'A clerk investigates missing mixed cargo and must own his misclassification.', record.notice, record.chapter_id))
        connection.execute('DELETE FROM story_choices WHERE chapter_id = ?', (record.chapter_id,))
        connection.execute('UPDATE scene_nodes SET node_order = node_order + 100 WHERE chapter_id = ?', (record.chapter_id,))
        connection.execute('DELETE FROM node_evidence WHERE node_id IN (SELECT node_id FROM scene_nodes WHERE chapter_id = ?)', (record.chapter_id,))
        for index, scene in enumerate(record.scenes, 1):
            node_id = self.NODE_IDS[scene.scene_id]
            slot_id = self.SLOT_IDS[scene.scene_id]
            photo = next(photo for photo in record.photos if photo.photo_id == scene.photo_id)
            connection.execute('UPDATE scene_nodes SET node_order = ?, title = ?, structure_id = ? WHERE node_id = ?',
                               (index, scene.title, photo.structure_id, node_id))
            connection.execute('INSERT INTO scene_photos (node_id, derivative_id) VALUES (?, ?)', (node_id, photo.photo_id))
            connection.executemany('INSERT INTO node_evidence (node_id, claim_id) VALUES (?, ?)',
                                   [(node_id, claim_id) for claim_id in scene.claim_ids])
            connection.execute('UPDATE task_slots SET node_id = ?, task_kind = ? WHERE slot_id = ?',
                               (node_id, _text(_mapping(json.loads(scene.task_json)).get('kind')), slot_id))
            connection.execute('''UPDATE task_candidates SET task_payload_json = ?
                WHERE task_id = (SELECT fallback_task_id FROM task_slots WHERE slot_id = ?)''', (scene.task_json, slot_id))
            fallback = connection.execute('SELECT fallback_task_id FROM task_slots WHERE slot_id = ?', (slot_id,)).fetchone()
            if fallback and fallback[0]:
                connection.execute('DELETE FROM task_candidate_claims WHERE task_id = ?', (fallback[0],))
                connection.executemany('INSERT INTO task_candidate_claims (task_id, claim_id) VALUES (?, ?)',
                                       [(fallback[0], claim_id) for claim_id in scene.claim_ids])
            if scene.decision:
                decision = scene.decision
                connection.execute('''INSERT INTO story_choices
                    (choice_id, chapter_id, node_id, choice_order, prompt, options_json, effects_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (decision.decision_id, record.chapter_id, node_id, index, decision.prompt,
                     decision.options_json, decision.effects_json))

    @classmethod
    def _validate(cls, connection: sqlite3.Connection, record: ChapterRecord, project_root: Path) -> None:
        if {scene.scene_id for scene in record.scenes} != set(cls.NODE_IDS):
            raise StoryImportError('The pilot requires five distinct playable scene IDs.')
        photo_ids = {photo.photo_id for photo in record.photos}
        if len(photo_ids) != len(record.photos):
            raise StoryImportError('Duplicate photograph IDs.')
        for photo in record.photos:
            if photo.pdf_page < 1 or photo.image_index < 0:
                raise StoryImportError('Invalid photograph locator.')
            local = (project_root / 'prototype' / photo.file_path).resolve()
            if project_root.resolve() not in local.parents or not local.is_file():
                raise StoryImportError(f'Missing or unsafe local photograph: {photo.file_path}')
            if connection.execute('SELECT 1 FROM sources WHERE source_id = ?', (photo.source_id,)).fetchone() is None:
                raise StoryImportError(f'Unknown photograph source: {photo.source_id}')
        for scene in record.scenes:
            if scene.photo_id not in photo_ids:
                raise StoryImportError(f'Unknown scene photograph: {scene.photo_id}')
            for claim_id in scene.claim_ids:
                if connection.execute("SELECT 1 FROM claims WHERE claim_id = ? AND publication_state = 'approved'", (claim_id,)).fetchone() is None:
                    raise StoryImportError(f'Unapproved scene fact: {claim_id}')
