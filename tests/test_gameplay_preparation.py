"""Gameplay planning preserves Story meaning and does not certify presentation."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from test_story_automation import material_fixture

from pastport.adapters.gameplay_catalog import load_gameplay_catalog
from pastport.adapters.gameplay_verifier import DemoGameplayVerifier
from pastport.application.gameplay_preparation import GameplayPreparer
from pastport.application.models import ServiceError
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.gameplay_preparation import (
    ActivityConfig,
    LifecycleReceipt,
    PluginIdentity,
    SourceReadingConfig,
    TilingConfig,
)
from pastport.domain.mechanics import CoverageProblem, SourceChoiceRequirement
from pastport.domain.modules import NarrativeDraft, TaskTilingIntent
from pastport.ports.gameplay_preparation import GameplayVerifier

ROOT = Path(__file__).resolve().parents[1]


def make_preparer(
    verifier: GameplayVerifier,
    plugin: PluginIdentity,
    additional_plugins: Mapping[str, PluginIdentity] | None = None,
) -> GameplayPreparer:
    return GameplayPreparer(
        verifier, plugin, additional_plugins, capabilities=load_gameplay_catalog()
    )


def with_tiling(story: NarrativeDraft, exercises: tuple[TaskTilingIntent, ...]) -> NarrativeDraft:
    replacements = {exercise.task_id: exercise for exercise in exercises}
    return story.model_copy(
        update={
            "gameplay_intents": tuple(
                replacements.get(intent.task_id, intent) for intent in story.gameplay_intents
            )
        }
    )


class SyntheticVerifier:
    def verify(self, config: ActivityConfig) -> LifecycleReceipt:
        return LifecycleReceipt(
            plugin_code_sha256="1" * 64,
            verifier_sha256="2" * 64,
            config_sha256=CanonicalSerializer.digest(config),
            checks=("synthetic_mapping_only",),
        )


def draft() -> NarrativeDraft:
    raw = (ROOT / "tests/fixtures/reference/draft-result.json").read_text()
    raw = (
        raw.replace('"claim-kitchen"', '"claim-object-1"')
        .replace('"asset-hatch"', '"object-1"')
        .replace('"hatch"', '"result"')
    )
    document = json.loads(raw)["payload"]
    for scene in document["package"]["game"]["scenes"]:
        for task in scene["tasks"]:
            if task["kind"] == "caseboard":
                del task["required_prop_ids"], task["answer_rule"]
                task.update(
                    kind="inspect",
                    asset_id="object-1",
                    required_spot_ids=["result"],
                    spots=[
                        dict(
                            spot_id="result",
                            x=0,
                            y=0,
                            text_key=task["objective_key"],
                            claim_ids=["claim-object-1"],
                        )
                    ],
                )
    document["capability_catalog_sha256"] = load_gameplay_catalog().sha256
    document["gameplay_intents"] = [
        dict(kind="source_reading", task_id=t["task_id"], capability_id="source-reading:1")
        for scene in document["package"]["game"]["scenes"]
        for t in scene["tasks"]
    ]
    document["spatial_intents"] = [
        dict(
            task_id=t["task_id"],
            object_number=1,
            view_id="one",
            station_id="spawn",
            interaction="inspect_linked_source",
        )
        for s in document["package"]["game"]["scenes"]
        for t in s["tasks"]
    ]
    return NarrativeDraft.model_validate_json(json.dumps(document))


def reference(value: NarrativeDraft) -> ArtifactRef:
    return CanonicalSerializer.reference(value.package, "test-story", "narrative")


def test_plan_is_deterministic_pinned_and_does_not_rewrite_story_or_guess_visibility(
    tmp_path: Path,
) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    before = CanonicalSerializer.digest(story)
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test-only.mjs", code_sha256="1" * 64
    )
    service = make_preparer(SyntheticVerifier(), plugin)
    plan = service.prepare(story, reference(story), inputs.museum, inputs.index, "3" * 64)
    assert plan.status == "prepared" and len(plan.bindings) == 2
    assert plan.playable is False and plan.global_state_committed is False and plan.model_calls == 0
    assert all(b.completion == "source_exposure_not_comprehension" for b in plan.bindings)
    assert all(b.scene_binding == "pending_presentation" for b in plan.bindings)
    assert all(
        not station.calibration_confirmed for b in plan.bindings for station in b.spatial_candidates
    )
    assert CanonicalSerializer.digest(story) == before
    assert service.prepare(story, reference(story), inputs.museum, inputs.index, "3" * 64) == plan


def test_stale_narrative_is_rejected_before_plugin_work(tmp_path: Path) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    stale = reference(story).model_copy(update={"sha256": "f" * 64})
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    with pytest.raises(ServiceError, match="identity differs"):
        make_preparer(SyntheticVerifier(), plugin).prepare(
            story, stale, inputs.museum, inputs.index, "3" * 64
        )


def test_unsupported_native_task_is_a_gap_not_a_weaker_reading_task(tmp_path: Path) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    raw = json.loads(story.model_dump_json())
    task = raw["package"]["game"]["scenes"][1]["tasks"][0]
    del task["asset_id"], task["spots"], task["required_spot_ids"]
    task.update(kind="caseboard", required_prop_ids=["delivery-note"], answer_rule="exact_set")
    story = NarrativeDraft.model_validate_json(json.dumps(raw))
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    plan = make_preparer(SyntheticVerifier(), plugin).prepare(
        story, reference(story), inputs.museum, inputs.index, "3" * 64
    )
    assert plan.status == "blocked" and len(plan.bindings) == 1
    assert plan.gaps[0].task_id == "check-record" and plan.gaps[0].code == "unsupported_task"


def test_real_local_plugin_checks_roundtrip_invalid_actions_and_completion() -> None:
    from pastport.domain.gameplay_preparation import LocalizedCopy, SourceReading

    config = SourceReadingConfig(
        items=(
            SourceReading(id="first", text=LocalizedCopy(zh="原文一", en="Source one")),
            SourceReading(id="second", text=LocalizedCopy(zh="原文二", en="Source two")),
        )
    )
    receipt = DemoGameplayVerifier(ROOT).verify(config)
    assert receipt.config_sha256 == CanonicalSerializer.digest(config)
    assert {
        "serialize_restore_each_step",
        "invalid_action_rejected",
        "repeat_completion_rejected",
    } <= set(receipt.checks)


def test_missing_metric_stations_are_gaps_not_assumed_access(tmp_path: Path) -> None:
    from pastport.domain.story_inputs import EnvironmentSnapshot

    inputs = material_fixture(tmp_path / "inputs")
    raw = json.loads(inputs.museum.model_dump_json())
    raw.update(metric_spatial=None, spatial_profile="panorama_positions_only")
    environment = EnvironmentSnapshot.model_validate_json(json.dumps(raw))
    story = draft()
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    with pytest.raises(ServiceError, match="spatial intent"):
        make_preparer(SyntheticVerifier(), plugin).prepare(
            story, reference(story), environment, inputs.index, "3" * 64
        )


def test_foreign_plugin_receipt_is_rejected(tmp_path: Path) -> None:
    class WrongReceipt(SyntheticVerifier):
        def verify(self, config: ActivityConfig) -> LifecycleReceipt:
            return super().verify(config).model_copy(update={"plugin_code_sha256": "f" * 64})

    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    with pytest.raises(ServiceError, match="another plugin"):
        make_preparer(WrongReceipt(), plugin).prepare(
            story, reference(story), inputs.museum, inputs.index, "3" * 64
        )


def test_serialized_config_tampering_cannot_keep_an_old_receipt(tmp_path: Path) -> None:
    from pastport.domain.gameplay_preparation import GameplayPlan

    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    plan = make_preparer(SyntheticVerifier(), plugin).prepare(
        story, reference(story), inputs.museum, inputs.index, "3" * 64
    )
    raw = json.loads(plan.model_dump_json())
    raw["bindings"][0]["config"]["items"][0]["text"]["en"] = "tampered content"
    with pytest.raises(ValueError, match="identity differs"):
        GameplayPlan.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "foreign_view", "foreign_object", "foreign_station"]
)
def test_explicit_spatial_binding_rejects_missing_or_foreign_ids(
    tmp_path: Path, mutation: str
) -> None:
    from pastport.application.story_authoring import StoryDraftInspector

    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    intents = list(story.spatial_intents)
    if mutation == "missing":
        intents.pop()
    elif mutation == "duplicate":
        intents.append(intents[0])
    else:
        field, value = {
            "foreign_view": ("view_id", "not-registered"),
            "foreign_object": ("object_number", 999),
            "foreign_station": ("station_id", "behind-glass"),
        }[mutation]
        intents[0] = intents[0].model_copy(update={field: value})
    changed = story.model_copy(update={"spatial_intents": tuple(intents)})
    assert StoryDraftInspector().spatial_issues(changed, inputs.museum)


def test_selected_station_and_full_draft_hash_are_preserved(tmp_path: Path) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    plan = make_preparer(SyntheticVerifier(), plugin).prepare(
        story, reference(story), inputs.museum, inputs.index, "3" * 64
    )
    assert plan.story_draft_sha256 == CanonicalSerializer.digest(story)
    assert all(b.selected_station.view_id == "one" for b in plan.bindings)
    assert all(not b.selected_station.calibration_confirmed for b in plan.bindings)


@pytest.mark.parametrize("connected", [True, False])
def test_second_view_selection_uses_explicit_intent_not_first_candidate(
    tmp_path: Path, connected: bool
) -> None:
    from pastport.domain.story_inputs import (
        EnvironmentSnapshot,
        EnvironmentSpatialRevision,
        MetricSpatialContent,
        MetricSpatialSnapshot,
        SpatialGeometryAssessment,
        SpatialNavigationLink,
        SpatialWorld,
    )

    inputs = material_fixture(tmp_path / "inputs")
    museum = inputs.museum
    assert museum.metric_spatial is not None
    first = museum.metric_spatial.worlds[0]
    assert first.geometry is not None and first.geometry.result is not None
    base = first.model_copy(update={"view_id": "two", "world_id": "world-two", "geometry": None})
    second = SpatialWorld.model_validate(
        base.model_dump()
        | {
            "geometry": first.geometry.model_copy(
                update={"input_sha256": CanonicalSerializer.digest(base)}
            )
        }
    )
    if connected:
        link = SpatialNavigationLink(
            hotspot_id="next",
            target_view_id="two",
            point=first.calibration.origin,
            version=1,
            arrival_yaw=0.0,
            arrival_pitch=0.0,
        )
        base = first.model_copy(update={"navigation": (link,), "geometry": None})
        result = first.geometry.result.model_copy(
            update={
                "objects": (
                    *first.geometry.result.objects,
                    first.geometry.result.objects[0].model_copy(update={"key": "arrow:next"}),
                )
            }
        )
        first = SpatialWorld.model_validate(
            base.model_dump()
            | {
                "geometry": SpatialGeometryAssessment(
                    algorithm_sha256=first.geometry.algorithm_sha256,
                    input_sha256=CanonicalSerializer.digest(base),
                    status="computed",
                    result=result,
                    limitation="Synthetic navigation counterpart",
                )
            }
        )
    views = (*museum.views, museum.views[0].model_copy(update={"view_id": "two"}))
    positions = (*museum.positions, museum.positions[0].model_copy(update={"view_id": "two"}))
    spatial = EnvironmentSpatialRevision(
        entry_view_id=museum.entry_view_id, views=views, positions=positions
    )
    content = MetricSpatialContent(worlds=(first, second), rules=museum.metric_spatial.rules)
    environment = EnvironmentSnapshot.model_validate(
        museum.model_dump()
        | {
            "views": views,
            "positions": positions,
            "spatial_revision": CanonicalSerializer.digest(spatial),
            "metric_spatial": MetricSpatialSnapshot(
                **content.model_dump(),
                revision=CanonicalSerializer.digest(content),
                assessment="geometry_computed",
            ),
        }
    )
    story = draft()
    story = story.model_copy(
        update={
            "spatial_intents": tuple(
                intent.model_copy(update={"view_id": "two"}) for intent in story.spatial_intents
            )
        }
    )
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    service = make_preparer(SyntheticVerifier(), plugin)
    if not connected:
        with pytest.raises(ServiceError, match="spatial intent"):
            service.prepare(story, reference(story), environment, inputs.index, "3" * 64)
    else:
        plan = service.prepare(story, reference(story), environment, inputs.index, "3" * 64)
        assert all(b.spatial_candidates[0].view_id == "one" for b in plan.bindings)
        assert all(b.selected_station.view_id == "two" for b in plan.bindings)


def test_explicit_tiling_intent_uses_registered_plugin_and_real_lifecycle(tmp_path: Path) -> None:
    from pastport.domain.modules import TaskTilingIntent

    inputs = material_fixture(tmp_path / "inputs")
    index = inputs.index.model_copy(
        update={
            "candidate_claims": (
                *inputs.index.candidate_claims,
                inputs.index.candidate_claims[0].model_copy(
                    update={
                        "claim_id": "claim-other",
                        "text": "A different synthetic corridor source",
                    }
                ),
            )
        }
    )
    story = draft()
    first = story.package.game.scenes[0].tasks[0].task_id
    story = with_tiling(
        story,
        (
            TaskTilingIntent(
                task_id=first,
                capability_id="source-gated-coverage:1",
                rules=CoverageProblem(width=4, height=4, pieces=((1, 4),) * 4),
                source_requirement=SourceChoiceRequirement(
                    target_claim_id="claim-object-1", contrast_claim_ids=("claim-other",)
                ),
                learning_goal="Fit limited protective panels after inspecting the roof source",
                fiction_notice="Illustrative modern conservation exercise, "
                "not a historic roof layout",
            ),
        ),
    )
    verifier = DemoGameplayVerifier(ROOT)
    service = make_preparer(
        verifier,
        verifier.identity(),
        {
            "pastport.activity.tiling": verifier.identity("tiling"),
        },
    )
    before = CanonicalSerializer.digest(story)
    plan = service.prepare(story, reference(story), inputs.museum, index, "3" * 64)
    binding = next(b for b in plan.bindings if b.task_id == first)
    assert binding.config.kind == "tiling"
    assert binding.plugin.plugin_id == "pastport.activity.tiling"
    assert binding.completion == "board_coverage"
    assert "partial_board_restores" in binding.lifecycle.checks
    assert "board_coverage_completes" in binding.lifecycle.checks
    assert binding.exercise_notice == story.tiling_intents[0].fiction_notice
    assert CanonicalSerializer.digest(story) == before
    assert plan.model_calls == 0 and not plan.playable


def test_tiling_without_registered_plugin_is_not_downgraded_to_reading(tmp_path: Path) -> None:
    from pastport.domain.modules import TaskTilingIntent

    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    first = story.package.game.scenes[0].tasks[0].task_id
    story = with_tiling(
        story,
        (
            TaskTilingIntent(
                task_id=first,
                capability_id="source-gated-coverage:1",
                rules=CoverageProblem(width=4, height=4, pieces=((1, 4),) * 4),
                source_requirement=SourceChoiceRequirement(
                    target_claim_id="claim-object-1", contrast_claim_ids=("claim-other",)
                ),
                learning_goal="Panel coverage",
                fiction_notice="Fictional conservation exercise",
            ),
        ),
    )
    plugin = PluginIdentity(
        plugin_id="pastport.activity.dialogue", entrypoint="test.mjs", code_sha256="1" * 64
    )
    plan = make_preparer(SyntheticVerifier(), plugin).prepare(
        story, reference(story), inputs.museum, inputs.index, "3" * 64
    )
    assert plan.status == "blocked"
    assert all(b.task_id != first for b in plan.bindings)
    assert any(g.task_id == first and g.code == "unsupported_task" for g in plan.gaps)


def test_neutral_task_rules_allow_four_strips_without_plugin_implementation_fields() -> None:
    from pastport.domain.modules import TaskTilingIntent

    raw = {
        "task_id": "roof",
        "capability_id": "source-gated-coverage:1",
        "learning_goal": "Model coverage",
        "fiction_notice": "Abstract exhibit only",
        "source_requirement": {
            "target_claim_id": "claim-object-1",
            "contrast_claim_ids": ["claim-other"],
        },
        "rules": {"width": 4, "height": 4, "pieces": [[1, 4]] * 4, "rotation_allowed": True},
    }
    task = TaskTilingIntent.model_validate_json(json.dumps(raw))
    capability = load_gameplay_catalog().profile(task.capability_id)
    assert capability is not None
    assert capability.accepts(task.rules)
    rules = raw["rules"]
    assert isinstance(rules, dict)
    rules["kind"] = "tiling"
    with pytest.raises(ValueError):
        TaskTilingIntent.model_validate_json(json.dumps(raw))


def source_gated_story() -> NarrativeDraft:
    from pastport.domain.modules import TaskTilingIntent

    story = draft()
    return with_tiling(
        story,
        (
            TaskTilingIntent(
                task_id=story.package.game.scenes[0].tasks[0].task_id,
                capability_id="source-gated-coverage:1",
                rules=CoverageProblem(width=4, height=4, pieces=((1, 4),) * 4),
                source_requirement=SourceChoiceRequirement(
                    target_claim_id="claim-object-1", contrast_claim_ids=("claim-other",)
                ),
                learning_goal="Distinguish the supported record before arranging a model",
                fiction_notice="An abstract modern exercise, not a historical reconstruction",
            ),
        ),
    )


def test_source_removal_and_wrong_target_cannot_become_a_generic_puzzle(tmp_path: Path) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = source_gated_story()
    verifier = DemoGameplayVerifier(ROOT)
    service = make_preparer(
        verifier, verifier.identity(), {"pastport.activity.tiling": verifier.identity("tiling")}
    )
    plan = service.prepare(story, reference(story), inputs.museum, inputs.index, "3" * 64)
    assert plan.status == "blocked"
    assert any("source grounding" in g.reason for g in plan.gaps)
    wrong = story.tiling_intents[0].model_copy(
        update={
            "source_requirement": SourceChoiceRequirement(
                target_claim_id="claim-other", contrast_claim_ids=("claim-object-1",)
            )
        }
    )
    changed = with_tiling(story, (wrong,))
    plan = service.prepare(changed, reference(changed), inputs.museum, inputs.index, "3" * 64)
    assert plan.status == "blocked"


def test_stale_catalog_is_rejected_before_plugin_execution(tmp_path: Path) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = source_gated_story().model_copy(update={"capability_catalog_sha256": "f" * 64})
    verifier = DemoGameplayVerifier(ROOT)
    with pytest.raises(ServiceError, match="another capability catalog"):
        make_preparer(verifier, verifier.identity()).prepare(
            story, reference(story), inputs.museum, inputs.index, "3" * 64
        )


def test_equal_area_without_a_solution_is_not_an_executable_task() -> None:
    config = TilingConfig(width=4, height=4, pieces=((3, 3), (2, 2), (1, 3)))
    with pytest.raises(ServiceError, match="rejected its configuration"):
        DemoGameplayVerifier(ROOT).verify(config)


@pytest.mark.parametrize("copy", ["请铺好六块板。", "Arrange six transparent panels."])
def test_story_copy_cannot_contradict_structured_inventory(copy: str) -> None:
    from pastport.application.task_copy import task_copy_issues

    story = source_gated_story()
    raw = json.loads(story.model_dump_json())
    key = raw["package"]["game"]["scenes"][0]["body_key"]
    for locale in raw["package"]["game"]["locales"]:
        for entry in locale["entries"]:
            if entry["key"] == key:
                entry["text"] = copy
    changed = NarrativeDraft.model_validate_json(json.dumps(raw))
    assert task_copy_issues(changed)


@pytest.mark.parametrize("change", ["missing", "duplicate"])
def test_no_implicit_reading_when_task_mechanic_is_missing_or_duplicated(
    tmp_path: Path, change: str
) -> None:
    inputs = material_fixture(tmp_path / "inputs")
    story = draft()
    intents = () if change == "missing" else (*story.gameplay_intents, story.gameplay_intents[0])
    changed = story.model_copy(update={"gameplay_intents": intents})
    verifier = DemoGameplayVerifier(ROOT)
    with pytest.raises(ServiceError, match="explicitly declare"):
        make_preparer(verifier, verifier.identity()).prepare(
            changed, reference(changed), inputs.museum, inputs.index, "3" * 64
        )


def test_catalog_minimum_piece_count_is_actually_verified() -> None:
    receipt = DemoGameplayVerifier(ROOT).verify(TilingConfig(width=4, height=4, pieces=((4, 4),)))
    assert len(receipt.solution) == 1
    assert "single_piece_checkpoint_restores" in receipt.checks
