from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.build_database import BuildConfig, DatabaseBuildError, DatabaseBuilder


ROOT = Path(__file__).resolve().parents[1]


class DatabaseBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "pilot.sqlite3"
        config = BuildConfig(
            schema_path=ROOT / "data" / "schema.sql",
            seed_path=ROOT / "data" / "seed.sql",
            media_manifest_path=ROOT / "data" / "media_manifest.csv",
            drive_file_ids_path=ROOT / "data" / "drive_file_ids.csv",
            database_path=self.database_path,
        )
        DatabaseBuilder().build(config)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_seed_has_a_complete_playable_chapter(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scene_nodes").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0], 93)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM story_choices").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM characters").fetchone()[0], 2)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertTrue(all(row[0] for row in connection.execute("SELECT fallback_task_id FROM task_slots WHERE ai_enabled = 1")))

    def test_photo_manifest_is_complete_and_has_unique_filenames(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            count, distinct_count = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT filename) FROM media_assets"
            ).fetchone()
            self.assertEqual(count, 93)
            self.assertEqual(distinct_count, 93)

    def test_manual_published_task_overrides_ai_candidate(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """INSERT INTO task_candidates
                   (task_id, slot_id, provider, state, version, priority, task_payload_json)
                   VALUES ('task-ai-test', 'slot-overview-map', 'ai', 'published', 2, 99, '{}')"""
            )
            selected = connection.execute(
                "SELECT task_id, provider FROM effective_tasks WHERE slot_id = 'slot-overview-map'"
            ).fetchone()
            self.assertEqual(selected, ("task-overview-fallback", "fallback"))
            connection.execute(
                "UPDATE task_candidates SET validation_state = 'passed' WHERE task_id = 'task-ai-test'"
            )
            connection.execute(
                "INSERT INTO task_candidate_claims (task_id, claim_id) VALUES ('task-ai-test', 'claim-katib-keeper')"
            )
            connection.execute(
                "INSERT INTO task_candidate_assets (task_id, asset_id) VALUES ('task-ai-test', 'asset-aerial-topdown')"
            )
            selected = connection.execute(
                "SELECT task_id, provider FROM effective_tasks WHERE slot_id = 'slot-overview-map'"
            ).fetchone()
            self.assertEqual(selected, ("task-overview-fallback", "fallback"))
            connection.execute(
                "UPDATE media_assets SET mapping_state = 'verified' WHERE asset_id = 'asset-aerial-topdown'"
            )
            selected = connection.execute(
                "SELECT task_id, provider FROM effective_tasks WHERE slot_id = 'slot-overview-map'"
            ).fetchone()
            self.assertEqual(selected, ("task-overview-fallback", "fallback"))
            connection.execute(
                "INSERT INTO node_evidence (node_id, claim_id, asset_id) VALUES ('node-overview', 'claim-katib-keeper', 'asset-aerial-topdown')"
            )
            selected = connection.execute(
                "SELECT task_id, provider FROM effective_tasks WHERE slot_id = 'slot-overview-map'"
            ).fetchone()
            self.assertEqual(selected, ("task-ai-test", "ai"))
            connection.execute(
                """INSERT INTO task_candidates
                   (task_id, slot_id, provider, state, version, priority, task_payload_json, approved_by)
                   VALUES ('task-manual-test', 'slot-overview-map', 'manual', 'published', 3, 1, '{}', 'editor')"""
            )
            selected = connection.execute(
                "SELECT task_id, provider FROM effective_tasks WHERE slot_id = 'slot-overview-map'"
            ).fetchone()
            self.assertEqual(selected, ("task-manual-test", "manual"))

    def test_browser_chapter_and_database_share_one_content_version(self) -> None:
        import hashlib
        payload = (ROOT / "data/muradiye-story.json").read_bytes()
        with sqlite3.connect(self.database_path) as connection:
            version, digest = connection.execute("SELECT version, content_sha256 FROM narrative_versions").fetchone()
            self.assertEqual(version, "muradiye-0.2.0")
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scene_photos").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_derivatives WHERE review_state = 'verified'").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT title FROM chapters").fetchone()[0], "最后两袋")

    def test_builder_refuses_to_overwrite_without_explicit_flag(self) -> None:
        config = BuildConfig(
            ROOT / "data/schema.sql",
            ROOT / "data/seed.sql",
            ROOT / "data/media_manifest.csv",
            ROOT / "data/drive_file_ids.csv",
            self.database_path,
        )
        with self.assertRaises(DatabaseBuildError):
            DatabaseBuilder().build(config)


if __name__ == "__main__":
    unittest.main()
