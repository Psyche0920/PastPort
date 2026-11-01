"""Story-only graph generates through its model port and never reaches game assembly."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from pastport.adapters.story_materials import StoryMaterialReader, StoryMaterials
from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.execution_models import ModelPolicy, ProviderRequest, ProviderResponse
from pastport.application.models import ServiceError
from pastport.application.story_authoring import StoryDraftInspector
from pastport.domain.common import CanonicalSerializer
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_inputs import (
    EnvironmentContentRevision,
    EnvironmentObject,
    EnvironmentPosition,
    EnvironmentQuote,
    EnvironmentSnapshot,
    EnvironmentSpatialRevision,
    EnvironmentView,
    MetricSpatialContent,
    MetricSpatialSnapshot,
    SpatialCalibration,
    SpatialGeometryAssessment,
    SpatialGeometryResult,
    SpatialObjectLocation,
    SpatialPoint,
    SpatialWorld,
)
from pastport.domain.workflow import SkillResult

ROOT = Path(__file__).resolve().parents[1]


def material_fixture(root: Path) -> StoryMaterials:
    root.mkdir()
    source = b"%PDF synthetic test bytes, not real history"
    digest = hashlib.sha256(source).hexdigest()
    quote = "The synthetic hatch is associated with the kitchen."
    (root / "original.pdf").write_bytes(source)
    (root / "document.json").write_text(
        json.dumps(
            {
                "source": {"project_id": "fixture-project", "asset": {"sha256": digest}},
                "page_count": 1,
                "pages": [
                    {"page_index": 0, "original_text": quote, "extraction_status": "text_extracted"}
                ],
            }
        )
    )
    obj = EnvironmentObject(
        object_number=1,
        stable_id="stable-one",
        historical_id="fixture-building/member",
        parent_number=None,
        name="Synthetic hatch",
        introduction=quote,
        introduction_version=0,
        pairing_version=0,
        image_review="unreviewed",
        text_review="unreviewed",
        proposal_state="candidate_unreviewed",
        evidence_limitation="Synthetic test only",
        quote=EnvironmentQuote(text=quote, pdf_page=1),
    )
    view = EnvironmentView(
        view_id="one",
        source_view_id="original-one",
        panorama_sha256="c" * 64,
        panorama_revision=1,
        navigation_targets=(),
    )
    position = EnvironmentPosition(
        object_number=1, view_id="one", yaw=0.0, pitch=0.0, version=0, placement="candidate"
    )
    origin = SpatialPoint(x=0.0, y=1.6, z=0.0)
    world = SpatialWorld(
        view_id="one",
        world_id="world-one",
        scene_binding="a" * 64,
        world_binding="b" * 64,
        collider_sha256="d" * 64,
        coordinate_frame="three_metric_y_up",
        metric_scale_factor=1.0,
        ground_plane_offset=0.0,
        calibration=SpatialCalibration(
            origin=origin,
            yaw_degrees=0.0,
            pitch_degrees=0.0,
            roll_degrees=0.0,
            version=0,
            confirmed=False,
        ),
        objects=(
            SpatialObjectLocation(
                object_number=1,
                point=SpatialPoint(x=0.0, y=1.0, z=-2.0),
                basis="automatic_candidate",
                version=0,
            ),
        ),
        navigation=(),
    )
    result = SpatialGeometryResult.model_validate_json(
        json.dumps(
            {
                "policy_version": "pastport.geometry-direct/1",
                "spawn_ground": True,
                "spawn": origin.model_dump(),
                "eye_height": 1.6,
                "routes": [],
                "objects": [
                    {
                        "key": "object:1",
                        "route_status": "clear",
                        "route": [],
                        "sight": "clear_to_anchor",
                        "distance": 2.0,
                        "legibility": "unknown",
                        "touch": "unknown",
                        "planning": {
                            "basis": "registered_geometry_not_identity_approval",
                            "approach_station": "object:1",
                            "enabled_interactions": ["inspect"],
                            "detail_reading": "task_specific_requirement_missing",
                            "physical_touch": "host_touch_rule_not_registered",
                            "observation_positions": [
                                {
                                    "station": "spawn",
                                    "point": origin.model_dump(),
                                    "distance": 2.0,
                                    "sight": "clear_to_anchor",
                                }
                            ],
                        },
                    }
                ],
            }
        )
    )
    geometry = SpatialGeometryAssessment(
        algorithm_sha256="e" * 64,
        input_sha256=CanonicalSerializer.digest(world),
        status="computed",
        result=result,
        limitation="Synthetic geometry only",
    )
    world = SpatialWorld.model_validate(world.model_dump() | {"geometry": geometry})
    from pastport.domain.story_inputs import SpatialTaskRules

    content = MetricSpatialContent(worlds=(world,), rules=SpatialTaskRules())
    metric = MetricSpatialSnapshot(
        worlds=content.worlds,
        rules=content.rules,
        revision=CanonicalSerializer.digest(content),
        assessment="geometry_computed",
    )
    snapshot = EnvironmentSnapshot(
        project_id="fixture-project",
        environment_id="fixture-site",
        import_manifest_sha256="f" * 64,
        source_pdf_sha256=digest,
        content_revision=CanonicalSerializer.digest(EnvironmentContentRevision(objects=(obj,))),
        spatial_revision=CanonicalSerializer.digest(
            EnvironmentSpatialRevision(entry_view_id="one", views=(view,), positions=(position,))
        ),
        entry_view_id="one",
        views=(view,),
        objects=(obj,),
        positions=(position,),
        issues=(),
        spatial_profile="metric_3d_source_bound",
        metric_spatial=metric,
    )
    (root / "environment.json").write_text(snapshot.model_dump_json())
    (root / "media").mkdir()
    (root / "media/history-01.png").write_bytes(b"synthetic media")
    return StoryMaterialReader().read(
        root / "original.pdf", root / "document.json", root / "environment.json", root / "media"
    )


class ModelCounterpart:
    def __init__(self, invalid: bool = False, dead_write: bool = False) -> None:
        self.calls = 0
        self.invalid = invalid
        self.dead_write = dead_write

    async def respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        del timeout_seconds
        self.calls += 1
        assert "museum" in request.input_text and "original-pdf" in request.input_text
        assert "gameplay_capabilities" in request.input_text
        schema = json.loads(request.output_schema_json)
        reference_keys = schema["$defs"]["AuthoringTaskReport"]["properties"]["heritage_refs"][
            "items"
        ]["enum"]
        assert "object-1" in reference_keys and "claim-object-1" in reference_keys
        assert all(not key.startswith("object:") for key in reference_keys)
        # The prompt does not ask the model to reproduce the native identity.
        assert '"stable_id"' not in request.input_text
        if self.invalid:
            output = "{}"
        else:
            envelope = json.loads(request.input_text)
            parent = envelope["parent_request"]
            raw = (ROOT / "tests/fixtures/reference/draft-result.json").read_text()
            raw = (
                raw.replace("claim-kitchen", "claim-object-1")
                .replace("asset-hatch", "object-1")
                .replace("source-1", "original-pdf")
            )
            draft = json.loads(raw)["payload"]
            draft["package"]["project_id"] = "fixture-project"
            draft["package"]["candidate_id"] = parent["selected_candidate"]["candidate_id"]
            draft["package"]["evidence_package_hash"] = parent["evidence"]["evidence_ref"]["sha256"]
            draft["package"]["routes"] = [parent["evidence"]["approved_route_ref"]]
            from pastport.adapters.gameplay_catalog import load_gameplay_catalog

            draft["capability_catalog_sha256"] = load_gameplay_catalog().sha256
            draft["gameplay_intents"] = [
                dict(kind="source_reading", task_id=t["task_id"], capability_id="source-reading:1")
                for scene in draft["package"]["game"]["scenes"]
                for t in scene["tasks"]
            ]
            draft["spatial_intents"] = [
                dict(
                    task_id=t["task_id"],
                    object_number=1,
                    view_id="one",
                    station_id="spawn",
                    interaction="inspect_linked_source",
                )
                for s in draft["package"]["game"]["scenes"]
                for t in s["tasks"]
            ]
            template = draft["authoring_report"][0]
            for scene in draft["package"]["game"]["scenes"]:
                scene["site_id"] = "fixture-site"
                for task in scene["tasks"]:
                    if not any(r["task_id"] == task["task_id"] for r in draft["authoring_report"]):
                        draft["authoring_report"].append(dict(template, task_id=task["task_id"]))
            if self.dead_write:
                draft["package"]["game"]["rules"][0]["effects"].append(
                    {"kind": "set_variable", "name": "unused-model-state", "value": True}
                )
            output = json.dumps(
                {
                    "request_id": envelope["request_id"],
                    "skill": "narrative",
                    "mode": "draft",
                    "input_refs": envelope["input_refs"],
                    "decision": "complete",
                    "payload": draft,
                    "issues": [],
                    "evidence_requests": [],
                    "changed_ids": [],
                    "reason": "Explicit synthetic test counterpart",
                    "reason_code": "TEST_COMPLETED",
                    "tool_request": None,
                }
            )
        if not self.invalid and not self.dead_write:
            SkillResult[NarrativeDraft].model_validate_json(output)
        return ProviderResponse(
            raw_json='{"test":true}',
            output_text=output,
            provider_request_id="test-request",
            input_tokens=100,
            output_tokens=100,
            error_code=None,
        )


def test_story_only_generates_exports_and_resumes_without_another_model_call(
    tmp_path: Path,
) -> None:
    materials = material_fixture(tmp_path / "inputs")
    provider = ModelCounterpart()
    runner = StoryAutomationWorkflow(
        materials,
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic scope only",
        provider,
        structure_profile="authored_graph",
    )
    result = asyncio.run(runner.run())
    assert result.is_file()
    assert provider.calls == 1
    assert not (tmp_path / "out/runtime.json").exists()
    assert json.loads((tmp_path / "out/story-check.json").read_text())["status"] == "ready"
    asyncio.run(runner.run())
    assert provider.calls == 1


def test_failed_model_is_accounted_for_and_not_implicitly_retried(tmp_path: Path) -> None:
    materials = material_fixture(tmp_path / "inputs")
    provider = ModelCounterpart(invalid=True)
    runner = StoryAutomationWorkflow(
        materials,
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic scope only",
        provider,
        structure_profile="authored_graph",
    )
    with pytest.raises(ServiceError):
        asyncio.run(runner.run())
    assert provider.calls == 1
    assert (tmp_path / "out/executions.json").exists()
    with pytest.raises(ServiceError):
        asyncio.run(runner.run())
    assert provider.calls == 1


def test_input_change_requires_a_new_run_before_model_dispatch(tmp_path: Path) -> None:
    material_fixture(tmp_path / "inputs")
    original = tmp_path / "inputs/original.pdf"
    original.write_bytes(b"changed")
    with pytest.raises(ServiceError, match="different identity"):
        StoryMaterialReader().read(
            original,
            tmp_path / "inputs/document.json",
            tmp_path / "inputs/environment.json",
            tmp_path / "inputs/media",
        )


def test_codex_policy_accepts_sol_and_rejects_the_old_luna_configuration() -> None:
    policy = ModelPolicy(
        role="story",
        provider="codex",
        model="gpt-6.1-sol",
        price_version="account-quota",
        input_microusd_per_million=0,
        output_microusd_per_million=0,
    )
    assert policy.model == "gpt-6.1-sol"
    with pytest.raises(ValueError, match="Sol 6.1"):
        ModelPolicy.model_validate(policy.model_dump() | {"model": "gpt-6-luna"})


def test_saved_revalidation_keeps_provider_disabled_even_if_output_stays_invalid(
    tmp_path: Path,
) -> None:
    materials = material_fixture(tmp_path / "inputs")
    provider = ModelCounterpart(invalid=True)
    runner = StoryAutomationWorkflow(
        materials,
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic scope only",
        provider,
        structure_profile="authored_graph",
    )
    with pytest.raises(ServiceError):
        asyncio.run(runner.run())
    replay = StoryAutomationWorkflow(
        materials,
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic scope only",
        provider,
        revalidate_saved_response=True,
        structure_profile="authored_graph",
    )
    with pytest.raises(ServiceError):
        asyncio.run(replay.run())
    assert provider.calls == 1


def test_automatic_graph_reconciles_dead_state_in_the_first_run_without_extra_calls(
    tmp_path: Path,
) -> None:
    materials = material_fixture(tmp_path / "inputs")
    provider = ModelCounterpart(dead_write=True)
    output = tmp_path / "out"
    result = asyncio.run(
        StoryAutomationWorkflow(
            materials,
            output,
            ROOT / "skills",
            "Synthetic state repair",
            provider,
            structure_profile="authored_graph",
        ).run()
    )
    assert result.is_file()
    assert provider.calls == 1
    audit = json.loads((output / "receipts/00-normalization.json").read_text())
    assert len(audit["state_repairs"]) == 1
    assert audit["state_repairs"][0]["name"] == "unused-model-state"
    assert not audit["state_issues"]
    assert "unused-model-state" in (output / "receipts/00.json").read_text()
    assert "unused-model-state" not in (output / "narrative-draft.json").read_text()
    assert json.loads((output / "story-check.json").read_text())["status"] == "ready"


def test_report_references_resolve_fiction_props_and_registered_heritage_namespaces(
    tmp_path: Path,
) -> None:
    materials = material_fixture(tmp_path / "inputs")
    output = tmp_path / "out"
    asyncio.run(
        StoryAutomationWorkflow(
            materials,
            output,
            ROOT / "skills",
            "Synthetic reference checks",
            ModelCounterpart(),
            structure_profile="authored_graph",
        ).run()
    )
    document = json.loads((output / "narrative-draft.json").read_text())
    report = document["authoring_report"][0]
    prop_id = document["package"]["game"]["props"][0]["prop_id"]
    report["premise_source_ids"].append(prop_id)
    report["heritage_refs"].append("fixture-building")
    inspector = StoryDraftInspector()
    draft = NarrativeDraft.model_validate_json(json.dumps(document))
    claims = frozenset(c.claim_id for c in materials.index.candidate_claims)
    sources = frozenset(s.source_id for s in materials.index.sources)
    assert inspector.inspect(draft, materials.museum, claims, sources).status == "ready"
    report["heritage_refs"].append("invented-building")
    bad = NarrativeDraft.model_validate_json(json.dumps(document))
    assert inspector.inspect(bad, materials.museum, claims, sources).status == "invalid"
    report["heritage_refs"].remove("invented-building")
    report["premise_source_ids"].append("invented-prop")
    bad = NarrativeDraft.model_validate_json(json.dumps(document))
    assert inspector.inspect(bad, materials.museum, claims, sources).status == "invalid"


def test_unknown_transport_exits_promptly_exports_receipt_and_never_retries(tmp_path: Path) -> None:
    import time

    class UnknownProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def respond(
            self, request: ProviderRequest, timeout_seconds: float
        ) -> ProviderResponse:
            self.calls += 1
            raise ServiceError("OUTCOME_UNKNOWN", "Synthetic unresolved transport")

    materials = material_fixture(tmp_path / "inputs")
    provider = UnknownProvider()
    output = tmp_path / "out"
    runner = StoryAutomationWorkflow(
        materials,
        output,
        ROOT / "skills",
        "Unknown receipt",
        provider,
        structure_profile="authored_graph",
    )
    before = time.monotonic()
    with pytest.raises(ServiceError, match="inspect saved receipts"):
        asyncio.run(runner.run())
    assert time.monotonic() - before < 10
    assert provider.calls == 1
    assert (output / "budget.json").exists()
    summaries = json.loads((output / "executions.json").read_text())
    assert len(summaries) == 1 and summaries[0]["error_code"] == "OUTCOME_UNKNOWN"
    assert summaries[0]["settlement"] is None
    with pytest.raises(ServiceError):
        asyncio.run(runner.run())
    assert provider.calls == 1


def test_report_may_use_exact_bound_object_without_duplicate_claim_id(tmp_path: Path) -> None:
    materials = material_fixture(tmp_path / "inputs")
    output = tmp_path / "out"
    asyncio.run(
        StoryAutomationWorkflow(
            materials,
            output,
            ROOT / "skills",
            "Task-linked evidence check",
            ModelCounterpart(),
            structure_profile="authored_graph",
        ).run()
    )
    document = json.loads((output / "narrative-draft.json").read_text())
    document["authoring_report"][0]["heritage_refs"] = [materials.museum.objects[0].stable_id]
    draft = NarrativeDraft.model_validate_json(json.dumps(document))
    claims = frozenset(c.claim_id for c in materials.index.candidate_claims)
    sources = frozenset(s.source_id for s in materials.index.sources)
    inspector = StoryDraftInspector()
    assert inspector.inspect(draft, materials.museum, claims, sources).status == "ready"
    document["authoring_report"][0]["heritage_refs"] = ["fixture-building"]
    draft = NarrativeDraft.model_validate_json(json.dumps(document))
    result = inspector.inspect(draft, materials.museum, claims, sources)
    assert result.status == "invalid"
    assert any("task-linked heritage evidence" in issue for issue in result.issues)


def test_environment_bytes_remain_locked_across_noncanonical_json_and_replay(
    tmp_path: Path,
) -> None:
    material_fixture(tmp_path / "inputs")
    root = tmp_path / "inputs"
    environment = root / "environment.json"
    original = json.dumps(json.loads(environment.read_text()), separators=(",", ":")).encode()
    environment.write_bytes(original)
    materials = StoryMaterialReader().read(
        root / "original.pdf", root / "document.json", environment, root / "media"
    )
    provider = ModelCounterpart()
    output = tmp_path / "out"
    runner = StoryAutomationWorkflow(
        materials,
        output,
        ROOT / "skills",
        "Synthetic scope only",
        provider,
        structure_profile="authored_graph",
    )
    asyncio.run(runner.run())
    assert (output / "environment-input.json").read_bytes() == original
    lock = json.loads((output / "input-lock.json").read_text())
    assert lock["environment_sha256"] == hashlib.sha256(original).hexdigest()
    # Reconcile an old, semantically identical formatted snapshot without another call.
    (output / "environment-input.json").write_text(json.dumps(json.loads(original), indent=2))
    asyncio.run(runner.run())
    assert provider.calls == 1
    assert (output / "environment-input.json").read_bytes() == original
    assert json.loads((output / "environment-serialization-receipt.json").read_text())[
        "semantic_content_unchanged"
    ]
