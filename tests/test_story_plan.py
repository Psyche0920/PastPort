"""Content-only model output compiles through the real metered workflow and JS engine."""

import asyncio
import json
import subprocess

import pytest
from pydantic import ValidationError
from test_story_automation import ROOT, material_fixture

from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.execution_models import ProviderResponse
from pastport.application.models import ServiceError
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_plan import StoryPlanResult


def words(en, zh):
    return {"en": en, "zh": zh}


def plan_fixture():
    from pastport.adapters.gameplay_catalog import load_gameplay_catalog

    task = {
        "asset_id": "object-1",
        "claim_ids": ["claim-object-1"],
        "view_id": "one",
        "title": words("Identify the hatch", "辨认窗口"),
        "dialogue": words(
            "We must label this hatch before the visit.", "参观前我们得确认这个窗口的说明。"
        ),
        "objective": words("Read the kitchen hatch source.", "阅读厨房窗口的来源资料。"),
        "feedback": words(
            "The record links the hatch to the kitchen; we can label it.",
            "记录把窗口与厨房联系起来，我们可以据此写标签。",
        ),
        "hints": [words("Look for kitchen in the source.", "在资料中找到厨房的描述。")],
        "accessibility": words("Read the linked text.", "可阅读关联文字。"),
        "gameplay": {"kind": "source_reading"},
        "reasoning": {
            "property_used": "The source links this hatch to a kitchen.",
            "player_premises": ["The linked record identifies a kitchen hatch."],
            "inference_steps": ["Compare the label with that specific source."],
            "accepted_answer": "Read the registered kitchen hatch source.",
            "removal_test": "Without this hatch record the label cannot be justified.",
            "substitution_test": "A different building record would not identify this hatch.",
            "counterexample": "A generic opening alone does not prove a kitchen.",
        },
    }
    return {
        "decision": "complete",
        "reason": "Synthetic plan with explicit source reading.",
        "plan": {
            "structure": "compiled_plan_v1",
            "protagonist_name": words("Guide", "讲解员"),
            "protagonist_goal": words("Prepare an accurate label", "准备准确的标签"),
            "tasks": [task, task],
            "choices": [
                {
                    "label": words("Show the source", "展示来源"),
                    "consequence": words(
                        "The visit proceeds with the source visible.", "参观继续，并展示来源。"
                    ),
                },
                {
                    "label": words("Delay the label", "暂缓标签"),
                    "consequence": words(
                        "The group waits while the label is checked.", "小组等待进一步核对标签。"
                    ),
                },
            ],
            "fiction_notice": "Synthetic original fiction, not history approval.",
            "capability_catalog_sha256": load_gameplay_catalog().sha256,
            "unresolved_items": ["Synthetic fixture only."],
        },
    }


class PlanProvider:
    def __init__(self, invalid=False):
        self.calls = 0
        self.invalid = invalid
        self.schema = None

    async def respond(self, request, timeout_seconds):
        self.calls += 1
        self.schema = json.loads(request.output_schema_json)
        assert "StoryPlan" in self.schema["$defs"]
        assert "Rule" not in self.schema["$defs"]
        assert "Variable" not in self.schema["$defs"]
        assert "museum" in request.input_text and "gameplay_capabilities" in request.input_text
        selectable = self.schema["$defs"]["StoryPlanTask"]["properties"]
        assert "object-1" in selectable["asset_id"]["enum"]
        assert "claim-object-1" in selectable["claim_ids"]["items"]["enum"]
        output = plan_fixture()
        if self.invalid:
            output["plan"]["rules"] = [{"target_id": "unused"}]
        return ProviderResponse(
            raw_json="{}",
            output_text=json.dumps(output),
            provider_request_id="synthetic-plan",
            input_tokens=100,
            output_tokens=100,
            error_code=None,
        )


def test_content_plan_generates_and_resumes_without_a_second_call(tmp_path):
    provider = PlanProvider()
    runner = StoryAutomationWorkflow(
        material_fixture(tmp_path / "inputs"),
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic scope only",
        provider,
    )
    asyncio.run(runner.run())
    assert provider.calls == 1
    assert json.loads((tmp_path / "out/story-check.json").read_text())["status"] == "ready"
    draft = NarrativeDraft.model_validate_json((tmp_path / "out/narrative-draft.json").read_bytes())
    assert {v.name for v in draft.package.game.variables} == {
        "final-task-complete",
        "ending-choice",
    }
    assert [t.task_id for s in draft.package.game.scenes for t in s.tasks] == ["task-1", "task-2"]
    assert all(r.target_id != "unused" for r in draft.package.game.rules)
    for task, report, space, gameplay in zip(
        [t for s in draft.package.game.scenes for t in s.tasks],
        draft.authoring_report,
        draft.spatial_intents,
        draft.gameplay_intents,
        strict=True,
    ):
        assert task.task_id == report.task_id == space.task_id == gameplay.task_id
    assert {x.key for x in draft.package.game.locales[0].entries} == {
        x.key for x in draft.package.game.locales[1].entries
    }
    raw = json.loads((tmp_path / "out/receipts/00.json").read_text())["response"]["output_text"]
    assert "rules" not in json.loads(raw)["plan"]
    assert not (tmp_path / "out/receipts/00-validation.txt").exists()
    asyncio.run(runner.run())
    assert provider.calls == 1
    # The same browser runtime must execute both ordered tasks and each ending.
    package = json.loads((ROOT / "tests/fixtures/reference/runtime.json").read_text())
    package["game"] = draft.package.game.model_dump(mode="json")
    script = """
import {readFileSync} from 'node:fs';
import {PlayerContext} from './src/pastport/player/context.mjs';
import {PlayerRuntime} from './src/pastport/player/runtime.mjs';
import {contentHash} from './src/pastport/player/validation.mjs';
const pkg=JSON.parse(readFileSync(0,'utf8'));
const ref={artifact_id:'compiled-test',project_id:pkg.project_id,kind:'runtime',
 schema_version:pkg.schema_version,content_version:pkg.content_version,
 sha256:await contentHash(pkg)};
for (const option of ['option-1','option-2']) {
 const ctx=await PlayerContext.create(pkg,ref,'compiled-release');
 const engine=new PlayerRuntime(ctx);let state=ctx.initialState();
 const apply=async(kind,target,fields={})=>{
  state=(await engine.apply(state,{project_id:state.project_id,
   release_id:state.release_id,package_hash:state.package_hash,
   action:{kind,target_id:target,action_id:'action-'+state.revision,
   expected_revision:state.revision,...fields}})).state;
 };
 await apply('observe','task-1',{spot_id:'result'});await apply('advance','scene-2');
 await apply('observe','task-2',{spot_id:'result'});
 await apply('choose','final-choice',{option_id:option});
 if(state.ending_id!=='ending-'+option.split('-')[1])throw new Error('Wrong ending');
}
console.log('Both compiled endings passed');
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        input=json.dumps(package),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_fixed_plan_rejects_model_authored_runtime_rules_and_does_not_retry(tmp_path):
    provider = PlanProvider(invalid=True)
    runner = StoryAutomationWorkflow(
        material_fixture(tmp_path / "inputs"),
        tmp_path / "out",
        ROOT / "skills",
        "Synthetic scope only",
        provider,
    )
    with pytest.raises(ServiceError):
        asyncio.run(runner.run())
    assert provider.calls == 1
    assert (tmp_path / "out/receipts/00.json").exists()
    with pytest.raises(ServiceError):
        asyncio.run(runner.run())
    assert provider.calls == 1


def test_fixed_plan_requires_explicit_gameplay_and_preserves_infeasibility():
    output = plan_fixture()
    del output["plan"]["tasks"][0]["gameplay"]
    with pytest.raises(ValidationError):
        StoryPlanResult.model_validate_json(json.dumps(output))
    result = StoryPlanResult.model_validate_json(
        json.dumps(
            {
                "decision": "no_feasible_story",
                "reason": "No registered source supports the task.",
                "plan": None,
            }
        )
    )
    assert result.plan is None
