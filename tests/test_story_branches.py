"""Bounded middle branches execute through the metered test workflow and real player host."""

import asyncio
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_story_automation import ROOT, material_fixture
from test_story_plan import activity_fixture, opening_fixture, plan_fixture

from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.execution_models import ProviderRequest, ProviderResponse
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_plan import BranchStoryPlanResult, StoryPlanResult


def words(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def branch_fixture() -> dict[str, Any]:
    original = plan_fixture()["plan"]
    task = original["tasks"][0]
    branches = []
    for title, finding in [
        ("Public inquiry", "Recorded public admission"),
        ("Witness cooperation", "Authorized redacted testimony"),
        ("Technical trace", "Original version log"),
    ]:
        distinct = copy.deepcopy(task)
        distinct["title"] = words(title, title)
        distinct["dialogue"] = words("Synthetic investigation: " + title, title)
        branches.append(
            {
                "label": words(title, title),
                "tasks": [distinct],
                "finding": words(finding, finding),
                "reunion_feedback": words("At reunion: " + finding, finding),
                "ending_consequences": [
                    words(finding + ": disclosed", finding + ": disclosed"),
                    words(finding + ": withheld", finding + ": withheld"),
                ],
            }
        )
    return {
        "decision": "complete",
        "reason": "Synthetic offline branch test, not the approved story.",
        "plan": {
            **{k: v for k, v in original.items() if k != "tasks"},
            "structure": "compiled_branch_v1",
            "opening": [task],
            "investigations": branches,
            "reunion": [task],
        },
    }


class BranchProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        self.calls += 1
        schema = json.loads(request.output_schema_json)
        assert "BranchStoryPlan" in schema["$defs"]
        assert "Rule" not in schema["$defs"]
        assert "object-1" in schema["$defs"]["StoryPlanTask"]["properties"]["asset_id"]["enum"]
        return ProviderResponse(
            raw_json="{}",
            output_text=json.dumps(branch_fixture()),
            provider_request_id="synthetic-branches",
            input_tokens=100,
            output_tokens=100,
            error_code=None,
        )


def test_exclusive_branches_compile_resume_package_and_play(tmp_path: Path) -> None:
    provider = BranchProvider()
    runner = StoryAutomationWorkflow(
        material_fixture(tmp_path / "inputs"),
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic only",
        provider,
        structure_profile="compiled_branch_v1",
    )
    asyncio.run(runner.run())
    assert json.loads((tmp_path / "out/story-check.json").read_text())["status"] == "ready"
    assert not (tmp_path / "out/receipts/00-validation.txt").exists()
    lock = json.loads((tmp_path / "out/input-lock.json").read_text())
    assert lock["structure_profile"] == "compiled_branch_v1" and lock["compiler_sha256"]
    asyncio.run(runner.run())
    assert provider.calls == 1
    draft = NarrativeDraft.model_validate_json((tmp_path / "out/narrative-draft.json").read_bytes())
    from pastport.application.story_compiler import StoryPlanCompiler

    approved = BranchStoryPlanResult.model_validate_json(json.dumps(branch_fixture())).plan
    assert approved is not None
    revision = StoryPlanCompiler().compile_saved_revision(approved, draft)
    assert revision.package.evidence_package_hash == draft.package.evidence_package_hash
    assert revision.package.routes == draft.package.routes
    assert "Human-edited" in revision.unresolved_items[-1]
    public = branch_fixture()
    public["plan"]["opening_context"] = opening_fixture()
    public_plan = BranchStoryPlanResult.model_validate_json(json.dumps(public)).plan
    assert public_plan is not None
    onboarded = StoryPlanCompiler().compile_saved_revision(public_plan, draft)
    assert onboarded.package.game.rules == revision.package.game.rules
    assert onboarded.spatial_intents == revision.spatial_intents
    assert any(
        entry.key == "presentation.opening_v1"
        for entry in onboarded.package.game.locales[0].entries
    )

    unregistered = branch_fixture()
    unregistered["plan"]["opening"][0]["claim_ids"] = ["unregistered-claim"]
    changed = BranchStoryPlanResult.model_validate_json(json.dumps(unregistered)).plan
    assert changed is not None
    with pytest.raises(ValueError, match="unregistered"):
        StoryPlanCompiler().compile_saved_revision(changed, draft)
    game = draft.package.game
    assert len(game.scenes) == 5
    assert game.scenes[0].next_scene_ids == ("scene-2", "scene-3", "scene-4")
    assert all(s.next_scene_ids == ("scene-5",) for s in game.scenes[1:4])
    assert len(game.props) == 3
    assert {x.key for x in game.locales[0].entries} == {x.key for x in game.locales[1].entries}
    script = (ROOT / "tests/game/compiled-branches.mjs").read_text()
    package = json.loads((ROOT / "tests/fixtures/reference/runtime.json").read_text())
    package["game"] = game.model_dump(mode="json")
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        input=json.dumps(package),
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_branch_contract_is_bounded_and_does_not_mutate_v1() -> None:
    data = branch_fixture()
    assert BranchStoryPlanResult.model_validate_json(json.dumps(data)).plan is not None
    with pytest.raises(ValidationError):
        StoryPlanResult.model_validate_json(json.dumps(data))
    data["plan"]["investigations"][0]["ending_consequences"].pop()
    with pytest.raises(ValidationError):
        BranchStoryPlanResult.model_validate_json(json.dumps(data))
    data = branch_fixture()
    data["plan"]["investigations"][0]["variables"] = ["invented"]
    with pytest.raises(ValidationError):
        BranchStoryPlanResult.model_validate_json(json.dumps(data))


def test_branch_activity_design_rejects_decision_anchor_but_accepts_exclusive_route() -> None:
    data = branch_fixture()
    data["plan"]["activity_design"] = activity_fixture()
    with pytest.raises(ValidationError, match="non-decision"):
        BranchStoryPlanResult.model_validate_json(json.dumps(data))
    data["plan"]["activity_design"]["interludes"][0]["after_task"] = 2
    assert BranchStoryPlanResult.model_validate_json(json.dumps(data)).plan is not None
