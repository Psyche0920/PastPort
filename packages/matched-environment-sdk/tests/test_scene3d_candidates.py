"""Automatic proposals must remain separate from authoritative human anchors."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pastport_matched_environment.api.scene3d import Scene3DStore
from pastport_matched_environment.domain.scene3d import SceneCandidateBatch


class CandidatePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        folder = self.root / "scene3d"
        folder.mkdir()
        (folder / "attachment.json").write_text(
            json.dumps(
                {
                    "binding": "fixture-binding",
                    "source_hotspots": [{"object_id": 1}],
                }
            )
        )
        self.store = Scene3DStore(self.root)
        self.store.initialize_candidates()
        with closing(sqlite3.connect(self.store.database)) as db, db:
            db.executescript("""
                CREATE TABLE scene3d_alignment(id INTEGER,version INTEGER,payload_json TEXT);
                CREATE TABLE pairings(modern_id INTEGER,historical_id TEXT,image_review TEXT,
                    text_review TEXT,proposal_state TEXT);
                CREATE TABLE scene3d_anchors(object_id INTEGER,point_json TEXT);
                INSERT INTO pairings VALUES
                    (1,'H1','unreviewed','unreviewed','candidate_unreviewed');
                INSERT INTO scene3d_anchors VALUES (1,'human-coordinate-must-survive');
            """)
            db.execute(
                "INSERT INTO scene3d_alignment VALUES (1,0,?)", (json.dumps({"confirmed": False}),)
            )
        self.batch = SceneCandidateBatch.model_validate_json(
            json.dumps(
                {
                    "scene_binding": "fixture-binding",
                    "alignment_version": 0,
                    "origin": {"x": 0.0, "y": 0.5, "z": 0.0},
                    "alignment_kind": "unconfirmed_asset_origin",
                    "positions": [{"object_id": 1, "point": {"x": 1.0, "y": 2.0, "z": 3.0}}],
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_proposals_are_idempotent_and_do_not_overwrite_human_coordinates(self) -> None:
        self.assertTrue(self.store.save_candidates(self.batch))
        self.assertTrue(self.store.save_candidates(self.batch))
        with closing(sqlite3.connect(self.store.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM scene3d_candidates").fetchone(), (1,))
            self.assertEqual(
                db.execute("SELECT point_json FROM scene3d_anchors").fetchone(),
                ("human-coordinate-must-survive",),
            )

    def test_stale_alignment_and_foreign_scene_cannot_publish_candidates(self) -> None:
        self.assertFalse(
            self.store.save_candidates(self.batch.model_copy(update={"alignment_version": 1}))
        )
        with self.assertRaises(ValueError):
            self.store.save_candidates(self.batch.model_copy(update={"scene_binding": "other"}))
        with closing(sqlite3.connect(self.store.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM scene3d_candidates").fetchone(), (0,))
