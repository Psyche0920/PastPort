import tempfile
import unittest
from pathlib import Path

from pastport_pdf_vr.adapters.identity import IdentityConflict, SQLiteSceneRepository
from pastport_pdf_vr.application.recognition import (
    RecognitionValidationError,
    SceneRecognitionService,
)
from pastport_pdf_vr.domain.recognition import (
    EntityProposal,
    RecognitionResult,
    SceneInspection,
    SceneInspectionRequest,
    SightingProposal,
)
from tests.support import sight, view


class FixtureInspector:
    """Explicit deterministic counterpart, never evidence of model recognition accuracy."""

    def __init__(self) -> None:
        self.calls = 0
        self.omit_recheck = False
        self.bad_image = False

    def inspect(self, request: SceneInspectionRequest) -> SceneInspection:
        self.calls += 1
        image = request.images[0].image_id
        if self.bad_image:
            image = "unprovided:image"
        if request.phase == "initial" and request.view_id == "point1":
            entities = tuple(
                EntityProposal(
                    proposal_id=key,
                    label=label,
                    category=category,
                    distinguishing_features=(feature,),
                )
                for key, label, category, feature in (
                    ("a", "Door A", "door", "Glass door with four panes"),
                    ("b", "Door B", "door", "White solid door"),
                    ("p", "Pillar", "column", "Vertical light strip"),
                    ("s", "Screen object", "device", "A view inside the laptop screen"),
                )
            )
            known = {entity.label: entity.object_id for entity in request.catalog}
            entities = tuple(
                proposal.model_copy(
                    update={
                        "existing_object_id": known[proposal.label],
                        "same_identity_evidence": (
                            "Fixture counterpart establishes the same hardware",
                        ),
                    }
                )
                if proposal.label in known
                else proposal
                for proposal in entities
            )
            return SceneInspection(
                entities=entities,
                sightings=(sight("a", image), sight("s", image, 250.0, "screen_content")),
                receipt_ref="fixture:initial1",
            )
        catalog = {entity.label: entity.object_id for entity in request.catalog}
        if request.phase == "initial":
            return SceneInspection(
                sightings=(sight(catalog["Door A"], image),), receipt_ref="fixture:initial2"
            )
        sightings = []
        for target in request.target_ids:
            if target == catalog["Pillar"]:
                if not self.omit_recheck:
                    sightings.append(sight(target, image, 230.0))
            elif target == catalog["Screen object"]:
                sightings.append(sight(target, image, 250.0, "screen_content"))
            else:
                sightings.append(
                    SightingProposal(
                        target_ref=target,
                        image_id=image,
                        disposition="not_seen",
                        basis=("Inspected detail without identifying this target",),
                    )
                )
        return SceneInspection(sightings=tuple(sightings), receipt_ref="fixture:detail")


class RecognitionTests(unittest.TestCase):
    def run_service(
        self,
        repository: SQLiteSceneRepository,
        inspector: FixtureInspector,
        binding: str = "sample",
        max_calls: int = 20,
        model_id: str = "fixture:vision-v1",
    ) -> RecognitionResult:
        return SceneRecognitionService(repository, inspector).run(
            "test",
            binding,
            (view("point1"), view("point2")),
            "fixture:grant",
            "scene-v1",
            "policy-v1",
            max_calls,
            model_id=model_id,
        )

    def test_all_views_stable_ids_distinct_doors_recheck_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteSceneRepository(Path(directory) / "scene.sqlite")
            model = FixtureInspector()
            result = self.run_service(repository, model)
            catalog = {entity.label: entity for entity in result.entities}
            self.assertNotEqual(catalog["Door A"].object_id, catalog["Door B"].object_id)
            self.assertEqual(len(result.dispositions), 8)
            for row in result.dispositions:
                if row.object_id == catalog["Door A"].object_id:
                    self.assertEqual(row.state, "located")
                elif row.object_id == catalog["Pillar"].object_id:
                    self.assertEqual(row.state, "located")
                    self.assertTrue(row.rechecked)
                elif row.object_id == catalog["Door B"].object_id:
                    self.assertEqual(row.state, "not_seen_after_review")
                    self.assertIsNone(row.position)
                else:
                    self.assertEqual(row.state, "screen_content")
                    self.assertIsNone(row.position)
            calls = model.calls
            again = self.run_service(repository, model)
            self.assertEqual(again.entities, result.entities)
            self.assertEqual(again.dispositions, result.dispositions)
            self.assertEqual(again.calls_used, 0)
            self.assertEqual(model.calls, calls)
            changed = self.run_service(repository, model, model_id="fixture:vision-v2")
            self.assertGreater(changed.calls_used, 0)
            self.assertEqual(changed.entities, result.entities)

            absent_id = catalog["Door B"].object_id
            absent = SceneRecognitionService(repository, model).run(
                "test",
                "sample",
                (view("point1"), view("point2")),
                "fixture:grant",
                "scene-v1",
                "policy-v1",
                20,
                frozenset({absent_id}),
                model_id="fixture:vision-v1",
            )
            self.assertTrue(
                all(
                    row.state == "confirmed_absent" and row.position is None
                    for row in absent.dispositions
                    if row.object_id == absent_id
                )
            )

    def test_omission_and_exhausted_budget_are_not_absence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteSceneRepository(Path(directory) / "scene.sqlite")
            model = FixtureInspector()
            model.omit_recheck = True
            result = self.run_service(repository, model)
            pillar = next(e.object_id for e in result.entities if e.label == "Pillar")
            self.assertTrue(
                all(
                    row.state == "not_inspected"
                    for row in result.dispositions
                    if row.object_id == pillar
                )
            )
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteSceneRepository(Path(directory) / "scene.sqlite")
            result = self.run_service(repository, FixtureInspector(), max_calls=1)
            self.assertEqual(result.calls_used, 1)
            self.assertTrue(result.gaps)
            self.assertTrue(
                all(
                    row.state == "not_inspected"
                    for row in result.dispositions
                    if row.view_id == "point2"
                )
            )

    def test_model_cannot_change_image_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteSceneRepository(Path(directory) / "scene.sqlite")
            model = FixtureInspector()
            model.bad_image = True
            with self.assertRaises(RecognitionValidationError):
                self.run_service(repository, model)
            self.assertEqual(repository.list_entities("test"), ())

    def test_identity_cycle_rolls_back_and_alias_rewrite_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteSceneRepository(Path(directory) / "scene.sqlite")

            def proposal(
                key: str, parent: str | None = None, label: str = "door"
            ) -> EntityProposal:
                return EntityProposal(
                    proposal_id=key,
                    label=label,
                    category="door",
                    distinguishing_features=("Distinct paint and hardware",),
                    parent_ref=parent,
                )

            with self.assertRaises(IdentityConflict):
                repository.resolve_proposals(
                    "test", "cycle", (proposal("a", "b"), proposal("b", "a"))
                )
            self.assertEqual(repository.list_entities("test"), ())
            first = repository.resolve_proposals("test", "run1", (proposal("a"),))
            self.assertEqual(first, repository.resolve_proposals("test", "run1", (proposal("a"),)))
            with self.assertRaises(IdentityConflict):
                repository.resolve_proposals("test", "run1", (proposal("a", label="changed"),))
            other = repository.resolve_proposals("other", "run1", (proposal("a"),))
            self.assertNotEqual(first["a"].object_id, other["a"].object_id)

    def test_seam_duplicates_share_one_identity_and_distant_points_remain_ambiguous(self) -> None:
        class SeamInspector:
            def __init__(self, x: float) -> None:
                self.x = x

            def inspect(self, request: SceneInspectionRequest) -> SceneInspection:
                entity = EntityProposal(
                    proposal_id="window",
                    label="Window",
                    category="window",
                    distinguishing_features=("Specific lintel and frame",),
                )
                target = entity.proposal_id if request.phase == "initial" else request.target_ids[0]
                return SceneInspection(
                    entities=(entity,) if request.phase == "initial" else (),
                    sightings=(
                        sight(target, request.images[0].image_id, 0.1),
                        sight(target, request.images[0].image_id, self.x),
                    ),
                    receipt_ref="fixture:seam",
                )

        for x, expected in ((399.9, "located"), (200.0, "ambiguous_position")):
            with tempfile.TemporaryDirectory() as directory:
                repository = SQLiteSceneRepository(Path(directory) / "scene.sqlite")
                result = SceneRecognitionService(repository, SeamInspector(x)).run(
                    "test",
                    "binding",
                    (view("point1"),),
                    "fixture:grant",
                    "scene-v1",
                    "policy-v1",
                    10,
                    model_id="fixture:vision-v1",
                )
                self.assertEqual(len(result.entities), 1)
                self.assertEqual(result.dispositions[0].state, expected)
