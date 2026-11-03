"""Count persisted eligible anchors, never candidate projection rows."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from pastport_matched_environment.api.scene3d import Scene3DStore


def test_saved_threshold_survives_reopen_and_ignores_candidates(tmp_path: Path) -> None:
    folder = tmp_path / "scene3d"
    folder.mkdir()
    numbers = (4, 5, 7, 8, 10, 13, 21, 22, 23, 24, 25, 26, 27, 28, 29)
    (folder / "attachment.json").write_text(json.dumps({
        "binding": "fixture-binding",
        "source_hotspots": [{"object_id": number} for number in (*numbers, 99)],
    }))
    store = Scene3DStore(tmp_path)
    store.initialize_candidates()
    with closing(sqlite3.connect(store.database)) as db, db:
        db.executescript("""
            CREATE TABLE scene3d_alignment(id INTEGER,version INTEGER,payload_json TEXT);
            INSERT INTO scene3d_alignment VALUES (1,0,'{}');
            CREATE TABLE modern_objects(id INTEGER,name TEXT,parent_id INTEGER);
            CREATE TABLE pairings(modern_id INTEGER,historical_id TEXT,version INTEGER,
                proposal_state TEXT,image_review TEXT,text_review TEXT);
            CREATE TABLE scene3d_anchors(object_id INTEGER,historical_id TEXT,version INTEGER,
                point_json TEXT,editor TEXT,identity_basis TEXT,relation_basis TEXT);
        """)
        for number in (*numbers, 99):
            db.execute("INSERT INTO modern_objects VALUES (?, 'fixture', NULL)", (number,))
            db.execute("INSERT INTO pairings VALUES (?, 'history', 0, 'candidate_unreviewed', ?, 'unreviewed')",
                       (number, "unsuitable" if number == 99 else "unreviewed"))
            db.execute("INSERT INTO scene3d_anchors VALUES (?, 'history', 1, ?, 'fixture', 'fixture', 'fixture')",
                       (number, '{"x":1,"y":2,"z":3}'))
            db.execute("INSERT INTO scene3d_candidates VALUES ('fixture-binding',0,?,?)",
                       (number, '{"x":9,"y":9,"z":9}'))
    progress = json.loads(Scene3DStore(tmp_path).current())["mounting_progress"]
    assert progress["saved"] == 15 and progress["minimum_saved_reached"] is True
    assert progress["saved_object_ids"] == sorted(numbers)
    with closing(sqlite3.connect(store.database)) as db, db:
        db.execute("UPDATE scene3d_anchors SET point_json=NULL WHERE object_id=29")
    reopened = json.loads(Scene3DStore(tmp_path).current())["mounting_progress"]
    assert reopened["saved"] == 14 and reopened["minimum_saved_reached"] is False
    assert reopened["missing_object_ids"] == [29]
    with closing(sqlite3.connect(store.database)) as db:
        assert db.execute("SELECT version,point_json FROM scene3d_anchors WHERE object_id=8").fetchone() == (
            1, '{"x":1,"y":2,"z":3}'
        )
