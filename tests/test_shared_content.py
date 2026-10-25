"""Shared identities/content must not collapse viewpoint state or divergent edits."""

import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pastport_pdf_vr.application.shared_content import (
    CONTENT_TABLES,
    SharedContentAuthority,
    SharedContentConflict,
)


class SharedContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "import-manifest.json").write_text('{"source":"one"}')
        with closing(sqlite3.connect(self.source / "pastport_matching.sqlite3")) as db, db:
            db.executescript("""
                CREATE TABLE modern_objects(id INTEGER PRIMARY KEY,stable_id TEXT);
                INSERT INTO modern_objects VALUES(1,'stable-one');
                CREATE TABLE pairings(modern_id INTEGER PRIMARY KEY,historical_id TEXT,
                    image_review TEXT,text_review TEXT,version INTEGER);
                INSERT INTO pairings VALUES(1,'H1','unreviewed','unreviewed',0);
                CREATE TABLE vr_display_contents(object_id INTEGER PRIMARY KEY,historical_id TEXT,
                    content TEXT,version INTEGER,updated_at TEXT,editor TEXT,
                    ai_draft TEXT,human_override TEXT);
                INSERT INTO vr_display_contents VALUES
                    (1,'H1','original',0,'t','seed','original',NULL);
                CREATE TABLE vr_content_events(id INTEGER PRIMARY KEY,object_id INTEGER,
                    old_content TEXT,new_content TEXT,previous_version INTEGER,
                    editor TEXT,created_at TEXT,event_type TEXT);
                CREATE TABLE review_events(id INTEGER PRIMARY KEY,modern_id INTEGER,
                    image_verdict TEXT,text_verdict TEXT,note TEXT,reviewer TEXT,
                    created_at TEXT,previous_version INTEGER);
                CREATE TABLE scene3d_anchors(object_id INTEGER,point_json TEXT);
                INSERT INTO scene3d_anchors VALUES(1,'source-position');
            """)
            for table in CONTENT_TABLES:
                db.execute(f"CREATE TABLE IF NOT EXISTS {table}(placeholder TEXT)")
        self.one, self.two = self.root / "one", self.root / "two"
        shutil.copytree(self.source, self.one)
        shutil.copytree(self.source, self.two)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def edit(root: Path, content: str) -> None:
        with closing(sqlite3.connect(root / "pastport_matching.sqlite3")) as db, db:
            old, version = db.execute(
                "SELECT content,version FROM vr_display_contents WHERE object_id=1"
            ).fetchone()
            db.execute(
                "UPDATE vr_display_contents SET content=?,human_override=?,version=version+1,"
                "editor='human',updated_at='edit' WHERE object_id=1",
                (content, content),
            )
            db.execute(
                "INSERT INTO vr_content_events(object_id,old_content,new_content,previous_version,"
                "editor,created_at,event_type) VALUES(1,?,?,?,'human','edit','human_edit')",
                (old, content, version),
            )

    def test_legacy_descendant_is_preserved_and_views_share_authority(self) -> None:
        self.edit(self.one, "preserved manual edit")
        first, second = SharedContentAuthority(self.one), SharedContentAuthority(self.two)
        first.bind(self.source)
        second.bind(self.source)
        self.edit(self.source, "new shared copy")
        for authority in (first, second):
            with authority.spatial_connection() as db:
                self.assertEqual(
                    db.execute("SELECT content FROM vr_display_contents").fetchone(),
                    ("new shared copy",),
                )
                self.assertEqual(
                    db.execute("SELECT count(*) FROM vr_content_events").fetchone(), (2,)
                )
        with closing(sqlite3.connect(self.one / "pastport_matching.sqlite3")) as db:
            self.assertEqual(
                db.execute("SELECT content FROM vr_display_contents").fetchone(),
                ("preserved manual edit",),
            )

    def test_divergence_is_atomic_and_retains_both_histories(self) -> None:
        self.edit(self.one, "local choice")
        self.edit(self.source, "source choice")
        with self.assertRaises(SharedContentConflict):
            SharedContentAuthority(self.one).bind(self.source)
        self.assertFalse((self.one / "shared-content.json").exists())
        with closing(sqlite3.connect(self.source / "pastport_matching.sqlite3")) as db:
            self.assertEqual(
                db.execute("SELECT content FROM vr_display_contents").fetchone(), ("source choice",)
            )

    def test_foreign_input_or_stable_identity_cannot_be_joined_by_number(self) -> None:
        (self.one / "import-manifest.json").write_text('{"source":"other"}')
        with self.assertRaises(ValueError):
            SharedContentAuthority(self.one).bind(self.source)
        shutil.copyfile(self.source / "import-manifest.json", self.one / "import-manifest.json")
        with closing(sqlite3.connect(self.one / "pastport_matching.sqlite3")) as db, db:
            db.execute("UPDATE modern_objects SET stable_id='another-object'")
        with self.assertRaises(ValueError):
            SharedContentAuthority(self.one).bind(self.source)

    def test_review_updates_are_shared_but_spatial_state_and_export_remain_local(self) -> None:
        authority = SharedContentAuthority(self.one)
        authority.bind(self.source)
        with authority.spatial_connection() as db, db:
            db.execute("UPDATE scene3d_anchors SET point_json='local-position'")
        with closing(sqlite3.connect(self.source / "pastport_matching.sqlite3")) as db, db:
            db.execute("UPDATE pairings SET image_review='unsuitable',version=1")
        with authority.spatial_connection() as db:
            self.assertEqual(
                db.execute("SELECT image_review FROM pairings").fetchone(), ("unsuitable",)
            )
            self.assertEqual(
                db.execute("SELECT point_json FROM scene3d_anchors").fetchone(), ("local-position",)
            )
        snapshot = self.root / "export.sqlite3"
        shutil.copyfile(self.one / "pastport_matching.sqlite3", snapshot)
        authority.snapshot_content(snapshot)
        with closing(sqlite3.connect(snapshot)) as db:
            self.assertEqual(
                db.execute("SELECT image_review FROM pairings").fetchone(), ("unsuitable",)
            )
            self.assertEqual(
                db.execute("SELECT point_json FROM scene3d_anchors").fetchone(), ("local-position",)
            )

    def test_missing_authority_fails_instead_of_falling_back_to_copy(self) -> None:
        authority = SharedContentAuthority(self.one)
        authority.bind(self.source)
        (self.source / "pastport_matching.sqlite3").rename(self.source / "retained.sqlite3")
        with self.assertRaises(sqlite3.Error):
            with authority.spatial_connection():
                self.fail("A missing authority must not use the stale copy")
