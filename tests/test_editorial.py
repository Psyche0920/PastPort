"""Saved human values survive model regeneration, stale edits and project/media changes."""

import tempfile
import unittest
from pathlib import Path

from pastport_pdf_vr.adapters.editorial import EditConflict, SQLiteEditorialRepository
from pastport_pdf_vr.domain.editorial import PositionEdit, PreviewAnchor, PreviewObject, TextEdit
from pastport_pdf_vr.domain.evidence import DisplayCopy
from pastport_pdf_vr.domain.geometry import AnchorPosition
from pastport_pdf_vr.domain.recognition import SceneEntity
from tests.support import asset


class EditorialTests(unittest.TestCase):
    def test_override_cas_idempotency_regeneration_media_and_reassignment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = SQLiteEditorialRepository(Path(directory) / "editorial.sqlite3")
            obj = PreviewObject(
                entity=SceneEntity(
                    object_id="object:1",
                    display_number=1,
                    label="Door",
                    category="door",
                    distinguishing_features=("Red frame",),
                ),
                historical_subject_id="portal",
                draft=DisplayCopy(subject_id="portal", version=1, introduction="AI text"),
            )
            anchor = PreviewAnchor(
                object_id="object:1",
                view_id="view:1",
                panorama=asset("pano"),
                panorama_revision=1,
                position=AnchorPosition(yaw=0.0, pitch=0.0),
            )
            other = anchor.model_copy(update={"view_id": "view:2"})
            repo.publish_proposals("test", "binding:1", "model_generated", (obj,), (anchor, other))
            text = TextEdit(
                operation_id="edit:text",
                object_id="object:1",
                historical_subject_id="portal",
                expected_version=0,
                introduction="Human text",
            )
            saved = repo.save_text("test", text)
            self.assertEqual(repo.save_text("test", text), saved)
            with self.assertRaises(EditConflict):
                repo.save_text("test", text.model_copy(update={"introduction": "Different reuse"}))
            with self.assertRaises(EditConflict):
                repo.save_text("test", text.model_copy(update={"operation_id": "stale"}))
            position = PositionEdit(
                operation_id="edit:position",
                object_id="object:1",
                view_id="view:1",
                panorama=anchor.panorama,
                panorama_revision=1,
                expected_version=0,
                position=AnchorPosition(yaw=20.0, pitch=15.0),
            )
            repo.save_position("test", position)
            position2 = position.model_copy(
                update={
                    "operation_id": "edit:position2",
                    "expected_version": 1,
                    "position": AnchorPosition(yaw=30.0, pitch=-10.0),
                }
            )
            repo.save_position("test", position2)
            changed_obj = obj.model_copy(
                update={
                    "draft": DisplayCopy(subject_id="portal", version=99, introduction="New AI")
                }
            )
            repo.publish_proposals(
                "test", "binding:2", "model_generated", (changed_obj,), (anchor, other)
            )
            snapshot = SQLiteEditorialRepository(Path(directory) / "editorial.sqlite3").snapshot(
                "test"
            )
            self.assertEqual(snapshot.objects[0].introduction, "Human text")
            self.assertEqual(snapshot.anchors[0].position, position2.position)
            self.assertEqual(snapshot.anchors[1].position, other.position)
            self.assertEqual(snapshot.anchors[0].version, 2)
            changed_anchor = anchor.model_copy(
                update={"panorama": asset("replacement"), "panorama_revision": 2}
            )
            changed_obj = obj.model_copy(
                update={"historical_subject_id": "fountain", "draft": None}
            )
            repo.publish_proposals(
                "test", "binding:3", "model_generated", (changed_obj,), (changed_anchor,)
            )
            current = repo.snapshot("test")
            self.assertTrue(current.objects[0].assignment_mismatch)
            self.assertEqual(current.objects[0].introduction, "")
            self.assertEqual(current.anchors[0].origin, "model")
            with self.assertRaises(EditConflict):
                repo.save_position(
                    "test", position2.model_copy(update={"operation_id": "old:media"})
                )
            with self.assertRaises(EditConflict):
                repo.save_text("test", text.model_copy(update={"operation_id": "old:subject"}))
