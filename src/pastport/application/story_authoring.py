"""Story-only checks and readable export; no plugin, frontend or assembly work."""

import re
from typing import Literal

from pydantic import Field

from pastport.application.task_copy import task_copy_issues
from pastport.domain.common import CanonicalSerializer, Contract, Identifier, Sha256, Text
from pastport.domain.mechanics import GameplayCapabilities
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_inputs import EnvironmentSnapshot


class StoryInputLock(Contract):
    structure_profile: Literal["authored_graph", "compiled_plan_v1", "compiled_branch_v1"] = (
        "authored_graph"
    )
    compiler_sha256: Sha256 | None = None
    project_id: Identifier
    original_pdf_sha256: Sha256
    source_document_sha256: Sha256
    environment_sha256: Sha256
    skill_sha256: Sha256
    capability_catalog_sha256: Sha256 | None = None
    source_index_sha256: Sha256 | None = None
    brief: Text
    model: Identifier = "gpt-6-luna"
    timeout_seconds: int = 120
    reasoning_effort: Literal["medium", "high"] = "medium"


class StoryAuthoringCheck(Contract):
    status: Literal["ready", "invalid"]
    narrative_sha256: Sha256
    story_draft_sha256: Sha256 | None = None
    issues: tuple[Text, ...]
    unresolved: tuple[Text, ...]
    acceptance: Literal["private_candidate_not_human_approved"] = (
        "private_candidate_not_human_approved"
    )


class StoryTaskBinding(Contract):
    task_id: Identifier
    object_number: int = Field(ge=1)
    view_id: Identifier
    station_id: Identifier = "spawn"
    action: Literal["inspect_linked_source"] = "inspect_linked_source"


class StoryDraftInspector:
    def inspect(
        self,
        draft: NarrativeDraft,
        museum: EnvironmentSnapshot,
        claim_ids: frozenset[str],
        source_ids: frozenset[str] = frozenset(),
        *,
        require_spatial_intents: bool = False,
        expected_catalog_sha256: str | None = None,
        capabilities: GameplayCapabilities | None = None,
    ) -> StoryAuthoringCheck:
        issues: list[str] = list(task_copy_issues(draft))
        if (
            expected_catalog_sha256 is not None
            and draft.capability_catalog_sha256 != expected_catalog_sha256
        ):
            issues.append("Story capability catalog identity is missing or stale")
        for exercise in draft.tiling_intents:
            capability = capabilities.profile(exercise.capability_id) if capabilities else None
            if capabilities is not None and (
                capability is None or not capability.accepts(exercise.rules)
            ):
                issues.append(f"Task {exercise.task_id} exceeds registered gameplay capability")
            requirement = exercise.source_requirement
            task = next(
                (
                    t
                    for s in draft.package.game.scenes
                    for t in s.tasks
                    if t.task_id == exercise.task_id
                ),
                None,
            )
            if (
                task is None
                or requirement.target_claim_id not in task.evidence_refs
                or not set(requirement.contrast_claim_ids) <= claim_ids
            ):
                issues.append(f"Task {exercise.task_id} has no grounded source-dependent challenge")
        if require_spatial_intents or draft.spatial_intents:
            issues.extend(self.spatial_issues(draft, museum))
        if draft.package.project_id != museum.project_id:
            issues.append("Story belongs to another project")
        tasks = {task.task_id: task for scene in draft.package.game.scenes for task in scene.tasks}
        reports = {report.task_id: report for report in draft.authoring_report}
        if set(tasks) != set(reports):
            issues.append("Task report coverage differs from the authored tasks")
        for task in tasks.values():
            if not set(task.evidence_refs) <= claim_ids:
                issues.append(f"Task {task.task_id} references unsupported source claims")
            if task.kind != "inspect":
                continue
            match = re.fullmatch(r"object-(\d+)", task.asset_id)
            obj = next(
                (o for o in museum.objects if match and o.object_number == int(match[1])), None
            )
            if obj is None or obj.proposal_state == "invalid_structural_relation":
                issues.append(f"Task {task.task_id} references an absent/excluded object")
                continue
            worlds = museum.metric_spatial.worlds if museum.metric_spatial else ()
            found = any(
                world.geometry
                and world.geometry.result
                and any(
                    node.key == f"object:{obj.object_number}"
                    and "inspect" in node.planning.enabled_interactions
                    and any(p.station == "spawn" for p in node.planning.observation_positions)
                    for node in world.geometry.result.objects
                )
                for world in worlds
            )
            if not found:
                issues.append(f"Task {task.task_id} has no registered source-inspection station")
        heritage_ids = set(claim_ids)
        for obj in museum.objects:
            if obj.proposal_state == "invalid_structural_relation":
                continue
            heritage_ids.update((obj.stable_id, f"object-{obj.object_number}"))
            if obj.historical_id is not None:
                heritage_ids.add(obj.historical_id)
                heritage_ids.add(obj.historical_id.split("/", 1)[0])
                # The Narrative Identifier wire profile excludes slashes. This
                # explicit alias maps back to the exact upstream historical ID.
                heritage_ids.add(obj.historical_id.replace("/", ":"))
        rule_ids = {rule.rule_id for rule in draft.package.game.rules}
        characters = {person.character_id for person in draft.package.game.characters}
        scenes = {scene.scene_id for scene in draft.package.game.scenes}
        premise_ids = (
            claim_ids | source_ids | frozenset(p.prop_id for p in draft.package.game.props)
        )
        for report in draft.authoring_report:
            if not set(report.heritage_refs) <= heritage_ids:
                issues.append(f"Task {report.task_id} has an unknown heritage reference")
            report_task = tasks.get(report.task_id)
            proof_ids = set(report_task.evidence_refs) if report_task is not None else set()
            related_objects = {
                obj.stable_id
                for obj in museum.objects
                if report_task is not None
                and (
                    f"claim-object-{obj.object_number}" in report_task.evidence_refs
                    or (
                        report_task.kind == "inspect"
                        and report_task.asset_id == f"object-{obj.object_number}"
                    )
                )
            }
            proof_ids.update(related_objects)
            if not set(report.heritage_refs) & proof_ids:
                issues.append(f"Task {report.task_id} has no task-linked heritage evidence")
            unrelated = {
                obj.stable_id
                for obj in museum.objects
                if (
                    obj.stable_id in report.heritage_refs
                    or f"object-{obj.object_number}" in report.heritage_refs
                )
                and obj.stable_id not in related_objects
            }
            if unrelated:
                issues.append(f"Task {report.task_id} has an unrelated heritage object")
            if not set(report.premise_source_ids) <= premise_ids:
                issues.append(
                    f"Task {report.task_id} has an unknown premise source or fiction prop"
                )
            if not set(report.effect_ids) <= rule_ids:
                issues.append(f"Task {report.task_id} has an unknown consequence rule")
            if report.character_goal not in characters:
                issues.append(f"Task {report.task_id} has an unknown character")
            if report.consequence_read_scene_id not in scenes:
                issues.append(f"Task {report.task_id} has an unknown consequence scene")
        return StoryAuthoringCheck(
            status="invalid" if issues else "ready",
            narrative_sha256=CanonicalSerializer.digest(draft.package),
            story_draft_sha256=CanonicalSerializer.digest(draft),
            issues=tuple(issues),
            unresolved=draft.unresolved_items,
        )

    def spatial_issues(self, draft: NarrativeDraft, museum: EnvironmentSnapshot) -> tuple[str, ...]:
        """Validate explicit task choices without selecting views from prose."""
        tasks = {task.task_id: task for scene in draft.package.game.scenes for task in scene.tasks}
        mechanics = {intent.task_id: intent for intent in draft.gameplay_intents}
        mechanic_issues = []
        if len(mechanics) != len(draft.gameplay_intents) or set(mechanics) != set(tasks):
            mechanic_issues.append("Every task must explicitly declare exactly one gameplay intent")
        intents = {intent.task_id: intent for intent in draft.spatial_intents}
        issues: list[str] = list(mechanic_issues)
        tiling_ids = [intent.task_id for intent in draft.tiling_intents]
        if len(tiling_ids) != len(set(tiling_ids)) or not set(tiling_ids) <= set(tasks):
            issues.append("Tiling intents must reference unique existing tasks")
        if len(intents) != len(draft.spatial_intents) or set(intents) != set(tasks):
            issues.append("Spatial intents must cover every task exactly once")
        worlds = (
            {w.view_id: w for w in museum.metric_spatial.worlds} if museum.metric_spatial else {}
        )
        reachable = {museum.entry_view_id}
        while True:
            following = reachable | {
                link.target_view_id
                for view in tuple(reachable)
                if view in worlds
                for link in worlds[view].navigation
                if link.target_view_id in worlds and link.point is not None
            }
            if following == reachable:
                break
            reachable = following
        for task_id, intent in intents.items():
            task = tasks.get(task_id)
            world = worlds.get(intent.view_id)
            if (
                task is None
                or (task.kind == "inspect" and task.asset_id != f"object-{intent.object_number}")
                or not any(
                    o.object_number == intent.object_number
                    and o.proposal_state != "invalid_structural_relation"
                    for o in museum.objects
                )
                or intent.view_id not in reachable
                or world is None
                or world.geometry is None
                or world.geometry.result is None
                or not world.geometry.result.spawn_ground
                or intent.station_id != "spawn"
            ):
                issues.append(f"Task {task_id} has an invalid spatial intent")
                continue
            node = next(
                (
                    n
                    for n in world.geometry.result.objects
                    if n.key == f"object:{intent.object_number}"
                ),
                None,
            )
            if (
                node is None
                or "inspect" not in node.planning.enabled_interactions
                or not any(
                    p.station == intent.station_id for p in node.planning.observation_positions
                )
            ):
                issues.append(f"Task {task_id} selected an unsupported inspection station")
        scenes = {scene.scene_id: scene for scene in draft.package.game.scenes}

        def transition(source_view: str, target_view: str) -> bool:
            if source_view == target_view:
                return True
            origin = worlds.get(source_view)
            return bool(
                origin
                and any(
                    link.target_view_id == target_view
                    and link.point is not None
                    and link.arrival_yaw is not None
                    and link.arrival_pitch is not None
                    for link in origin.navigation
                )
            )

        first_scene = scenes.get(draft.package.game.initial_state.current_scene_id)
        if first_scene and first_scene.tasks and first_scene.tasks[0].task_id in intents:
            if not transition(museum.entry_view_id, intents[first_scene.tasks[0].task_id].view_id):
                issues.append(
                    "Opening task has no registered transition from the environment entry"
                )
        for scene in scenes.values():
            if len(scene.tasks) != 1 or (
                len(scene.next_scene_ids) > 1
                and (scene.decision_id is None or len(scene.next_scene_ids) > 4)
            ):
                issues.append(f"Scene {scene.scene_id} exceeds the current executable task profile")
                continue
            origin = intents.get(scene.tasks[0].task_id)
            for target_id in scene.next_scene_ids:
                target_scene = scenes.get(target_id)
                target = (
                    intents.get(target_scene.tasks[0].task_id)
                    if target_scene and target_scene.tasks
                    else None
                )
                if origin and target and not transition(origin.view_id, target.view_id):
                    issues.append(
                        f"Scene {scene.scene_id} has no registered transition to {target_id}"
                    )
        return tuple(issues)

    def readable(self, draft: NarrativeDraft) -> str:
        table = next(locale for locale in draft.package.game.locales if locale.locale == "zh")
        text = {entry.key: entry.text for entry in table.entries}
        game = draft.package.game
        lines = ["# 故事与任务", "", "私有候选稿；史料、映射和空间原有状态保留。", ""]
        for index, scene in enumerate(game.scenes, 1):
            lines.extend((f"## {index}. {text[scene.title_key]}", "", text[scene.body_key], ""))
            for task in scene.tasks:
                lines.extend(
                    (
                        f"**玩家要做：** {text[task.objective_key]}",
                        f"**完成反馈：** {text[task.feedback_key]}",
                        "",
                    )
                )
            if scene.decision_id is not None:
                decision = next(d for d in game.decisions if d.decision_id == scene.decision_id)
                lines.extend(("**玩家选择：**", ""))
                lines.extend(f"- {text[option.text_key]}" for option in decision.options)
                lines.append("")
        lines.extend(("## 结局", ""))
        for group in game.endings:
            for ending in group.endings:
                for outcome in ending.outcomes:
                    lines.extend((f"### {text[outcome.label_key]}", text[outcome.text_key], ""))
        return "\n".join(lines)
