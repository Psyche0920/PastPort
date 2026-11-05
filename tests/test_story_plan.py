"""Content-only model output compiles through the real metered workflow and JS engine."""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_story_automation import ROOT, material_fixture

from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.execution_models import ProviderRequest, ProviderResponse
from pastport.application.models import ServiceError
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_plan import StoryPlanResult


def words(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def plan_fixture() -> dict[str, Any]:
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


def opening_fixture() -> dict[str, Any]:
    return {
        "title": words("The unfinished label", "未完成的标签"),
        "setting": words("Tonight at the museum kitchen", "今晚，馆内厨房"),
        "situation": words(
            "The new label needs checking before the visit.", "参观前要核对新标签。"
        ),
        "player_role": words(
            "You are the visiting guide, not an all-knowing witness.", "你是讲解员，并非全知证人。"
        ),
        "central_question": words(
            "What does this hatch actually establish?", "这个窗口实际证明什么？"
        ),
        "people": [
            {
                "name": words("Emma Reed", "叶晴"),
                "introduction": words(
                    "The source researcher you will meet.", "你将见到的来源研究员。"
                ),
            }
        ],
        "stations": [
            {
                "asset_id": "object-1",
                "title": words("Label-checking station", "标签核对位置"),
                "purpose": words(
                    "Compare the label with the hatch source.", "比较标签和窗口原始资料。"
                ),
            }
        ],
    }


def activity_fixture() -> dict[str, Any]:
    return {
        "asset_manifest": [],
        "interludes": [
            {
                "after_task": 1,
                "source_object": 1,
                "required_sources": [1],
                "title": words("Rebuild the inspection", "重組檢查次序"),
                "body": words(
                    "Compare the recorded order, not an invented time.",
                    "比較記錄次序，不捏造時間。",
                ),
                "objective": words("Arrange both inspection records.", "排列兩份檢查記錄。"),
                "opening_lines": [],
                "plugin": {
                    "kind": "timeline",
                    "content_kind": "original_fiction",
                    "prompt": words("Which record comes first?", "哪份記錄在先？"),
                    "success": words(
                        "The source was inspected before its label.", "先檢查來源，再檢查標籤。"
                    ),
                    "cards": [
                        {
                            "id": "label",
                            "text": words("Check label", "檢查標籤"),
                            "target_slot": "second",
                        },
                        {
                            "id": "source",
                            "text": words("Check source", "檢查來源"),
                            "target_slot": "first",
                        },
                    ],
                    "slots": [
                        {"id": "first", "label": words("First", "先")},
                        {"id": "second", "label": words("Second", "後")},
                    ],
                },
                "reward": words("Verified inspection order", "已核對的檢查次序"),
            }
        ],
    }


class PlanProvider:
    def __init__(
        self, invalid: bool = False, with_opening: bool = False, with_activity: bool = False
    ) -> None:
        self.calls = 0
        self.invalid = invalid
        self.with_opening = with_opening
        self.with_activity = with_activity
        self.schema: dict[str, Any] | None = None

    async def respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        self.calls += 1
        self.schema = json.loads(request.output_schema_json)
        assert self.schema is not None
        assert "StoryPlan" in self.schema["$defs"]
        assert "Rule" not in self.schema["$defs"]
        assert "Variable" not in self.schema["$defs"]
        assert "museum" in request.input_text and "gameplay_capabilities" in request.input_text
        selectable = self.schema["$defs"]["StoryPlanTask"]["properties"]
        assert "object-1" in selectable["asset_id"]["enum"]
        assert "claim-object-1" in selectable["claim_ids"]["items"]["enum"]
        output = plan_fixture()
        if self.with_opening:
            output["plan"]["opening_context"] = opening_fixture()
        if self.with_activity:
            output["plan"]["activity_design"] = activity_fixture()
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


@pytest.mark.parametrize(
    "with_opening,with_activity", [(False, False), (True, False), (True, True)]
)
def test_content_plan_generates_and_resumes_without_a_second_call(
    tmp_path: Path, with_opening: bool, with_activity: bool
) -> None:
    provider = PlanProvider(with_opening=with_opening, with_activity=with_activity)
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
const {storyPresentation}=await import('./gameplay/story-presentation.mjs');
const {embeddedInvestigationBlueprint}=
 await import('./tools/game-package/investigation-blueprint.mjs');
const design=embeddedInvestigationBlueprint({story:{kind:'runtime-package',payload:pkg}});
if(design){
 const row=design.interludes[0];
 if(row.after_scene_id!=='scene-1'||row.scene_id!=='investigation-scene-1'||
    row.plugin.kind!=='timeline'||row.reward.id!=='investigation-reward-1')
   throw Error('Compiler activity selection did not reach preparation');
}

const hasOpening=pkg.game.locales[0].entries.some(e=>e.key==='presentation.title');
const shown=storyPresentation({package:pkg},[{asset_object_number:1}],{legacy:true});
if(hasOpening){
 if(shown.briefing.sections.length!==4||shown.stationRecords[0].number!==1||
    shown.characterProfiles.length!==2)throw Error('Opening metadata did not reach the player');
 if(shown.stationRecords[0].reference_path)throw Error('Raw source download invented');
}
else if(!shown.legacy||shown.briefing)throw Error('Legacy output changed');
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


def test_fixed_plan_rejects_model_authored_runtime_rules_and_does_not_retry(tmp_path: Path) -> None:
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


def test_fixed_plan_requires_explicit_gameplay_and_preserves_infeasibility() -> None:
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


def test_opening_requires_exact_selected_objects_and_public_localized_names() -> None:
    output = plan_fixture()
    output["plan"]["opening_context"] = opening_fixture()
    result = StoryPlanResult.model_validate_json(json.dumps(output))
    assert result.plan is not None and result.plan.opening_context is not None
    output["plan"]["opening_context"]["stations"][0]["asset_id"] = "object-99"
    with pytest.raises(ValidationError, match="exactly"):
        StoryPlanResult.model_validate_json(json.dumps(output))
    output["plan"]["opening_context"] = opening_fixture()
    output["plan"]["opening_context"]["people"].append(
        output["plan"]["opening_context"]["people"][0]
    )
    with pytest.raises(ValidationError, match="distinct"):
        StoryPlanResult.model_validate_json(json.dumps(output))


@pytest.mark.parametrize(
    "mutation", ["foreign_object", "final_anchor", "duplicate_slot", "missing_picture"]
)
def test_activity_design_rejects_unbound_or_impossible_requests(mutation: str) -> None:
    data = plan_fixture()
    design = activity_fixture()
    data["plan"]["activity_design"] = design
    row = design["interludes"][0]
    if mutation == "foreign_object":
        row["source_object"] = 99
    elif mutation == "final_anchor":
        row["after_task"] = 2
    elif mutation == "duplicate_slot":
        row["plugin"]["cards"][0]["target_slot"] = "first"
    else:
        row["plugin"] = {
            "kind": "spot-difference",
            "content_kind": "original_fiction",
            "prompt": words("Compare", "比較"),
            "success": words("Found", "找到"),
            "left_image": "assets/missing.svg",
            "right_image": "assets/other.svg",
            "differences": [
                {
                    "id": "mark",
                    "left": [0, 0, 1000, 1000],
                    "right": [0, 0, 1000, 1000],
                    "label": words("Mark", "標記"),
                }
            ],
        }
    with pytest.raises(ValidationError):
        StoryPlanResult.model_validate_json(json.dumps(data))


def test_all_four_typed_patterns_share_registered_sources_and_checked_image_manifest() -> None:
    data = plan_fixture()
    data["plan"]["tasks"][1] = json.loads(json.dumps(data["plan"]["tasks"][1]))
    data["plan"]["tasks"][1]["asset_id"] = "object-2"
    data["plan"]["tasks"][1]["claim_ids"] = ["claim-object-2"]
    design = activity_fixture()
    paths = ["assets/left.svg", "assets/right.svg", "assets/chat-zh.svg", "assets/chat-en.svg"]
    design["asset_manifest"] = [
        {
            "path": path,
            "sha256": "a" * 64,
            "content_kind": "original_fiction",
            "source_claim_ids": [],
        }
        for path in paths
    ]
    common = {
        "prompt": words("Inspect", "檢查"),
        "success": words("Checked", "已核對"),
        "content_kind": "original_fiction",
    }
    plugins = [
        {
            **common,
            "kind": "spot-difference",
            "left_image": paths[0],
            "right_image": paths[1],
            "differences": [
                {
                    "id": "mark",
                    "left": [1000, 1000, 1000, 1000],
                    "right": [1000, 1000, 1000, 1000],
                    "label": words("Mark", "標記"),
                }
            ],
        },
        {
            **common,
            "kind": "image-puzzle",
            "image": {"zh": paths[2], "en": paths[3]},
            "columns": 2,
            "rows": 2,
            "pieces": [
                {"id": f"piece-{i}", "target_slot": slot} for i, slot in enumerate((2, 0, 3, 1))
            ],
        },
        {
            **common,
            "kind": "scene-search",
            "targets": [
                {"number": 1, "clue": words("First object", "第一件物件")},
                {"number": 2, "clue": words("Second object", "第二件物件")},
            ],
        },
    ]
    for plugin in plugins:
        row = {**design["interludes"][0], "plugin": plugin}
        if plugin["kind"] == "scene-search":
            row["required_sources"] = [1, 2]
        design["interludes"].append(row)
    data["plan"]["activity_design"] = design
    result = StoryPlanResult.model_validate_json(json.dumps(data)).plan
    assert result is not None and result.activity_design is not None
    assert len(result.activity_design.interludes) == 4
    # A real file check still belongs to preparation, not model JSON validation.
    design["asset_manifest"][0]["path"] = "assets/../private.svg"
    with pytest.raises(ValidationError):
        StoryPlanResult.model_validate_json(json.dumps(data))
