"""Compile explicit story choice bindings into the existing deterministic rule engine."""

from pydantic import Field

from pastport.application.updates import updated
from pastport.domain.common import Contract, Identifier
from pastport.domain.game import (
    AddStoryTime,
    All,
    AnyOf,
    ChoiceEquals,
    Effect,
    ObservedAll,
    ResolveEnding,
    Rule,
    SetVariable,
    UnlockScene,
)
from pastport.domain.modules import NarrativeDraft


class ChoiceBinding(Contract):
    decision_id: Identifier
    option_id: Identifier
    source_rule_id: Identifier


class StoryRuleBindings(Contract):
    choices: tuple[ChoiceBinding, ...] = Field(min_length=1)
    final_decision_id: Identifier
    ending_table_id: Identifier


class NarrativeRuleCompiler:
    """Keep story prose/effects; generate exclusive choices and task progression mechanics."""

    def compile(self, draft: NarrativeDraft, bindings: StoryRuleBindings) -> NarrativeDraft:
        game = draft.package.game
        decisions = {decision.decision_id: decision for decision in game.decisions}
        rules = {rule.rule_id: rule for rule in game.rules}
        expected = {
            (decision.decision_id, option.option_id)
            for decision in game.decisions
            for option in decision.options
        }
        supplied = {(item.decision_id, item.option_id) for item in bindings.choices}
        if supplied != expected or len(supplied) != len(bindings.choices):
            raise ValueError("Choice bindings must cover every exact decision/option once")
        if bindings.ending_table_id not in {table.ending_table_id for table in game.endings}:
            raise ValueError("Unknown ending table")
        final_scenes = [scene for scene in game.scenes if not scene.next_scene_ids]
        if len(final_scenes) != 1 or final_scenes[0].decision_id != bindings.final_decision_id:
            raise ValueError("The ending binding must name the sole terminal scene decision")
        compiled: list[Rule] = []
        for binding in bindings.choices:
            source = rules[binding.source_rule_id]
            if source.event != "option_chosen" or source.target_id != binding.decision_id:
                raise ValueError("A choice binding points to another event or decision")
            if not all(isinstance(effect, SetVariable) for effect in source.effects):
                raise ValueError("Choice intent may change state, not secretly alter progression")
            compiled.append(
                updated(
                    source,
                    guard=All(
                        kind="all",
                        conditions=(
                            source.guard,
                            ChoiceEquals(
                                kind="choice_equals",
                                decision_id=binding.decision_id,
                                option_id=binding.option_id,
                            ),
                        ),
                    ),
                )
            )
        task_rules: dict[str, str] = {}
        for scene in game.scenes:
            if len(scene.tasks) != 1 or len(scene.next_scene_ids) > 1:
                raise ValueError("The local host requires one task and a linear next scene")
            task = scene.tasks[0]
            if task.kind != "inspect":
                raise ValueError("This host requires an inspect result activity")
            state_effects: dict[str, SetVariable] = {}
            time_effects: dict[int, AddStoryTime] = {}
            for source in game.rules:
                if source.event != "task_completed" or source.target_id != task.task_id:
                    continue
                for effect in source.effects:
                    if isinstance(effect, SetVariable):
                        if effect.name in state_effects and state_effects[effect.name] != effect:
                            raise ValueError("Task progression contains conflicting state intent")
                        state_effects[effect.name] = effect
                    elif isinstance(effect, AddStoryTime):
                        time_effects[effect.minutes] = effect
            effects: list[Effect] = [*state_effects.values(), *time_effects.values()]
            effects.extend(
                UnlockScene(kind="unlock_scene", scene_id=next_id)
                for next_id in scene.next_scene_ids
            )
            if effects:
                ident = "complete:" + task.task_id
                task_rules[task.task_id] = ident
                compiled.append(
                    Rule(
                        rule_id=ident,
                        priority=10,
                        event="task_completed",
                        target_id=task.task_id,
                        guard=ObservedAll(
                            kind="observed_all",
                            scene_id=scene.scene_id,
                            spot_ids=task.required_spot_ids,
                        ),
                        effects=tuple(effects),
                        once_key=ident,
                    )
                )
        ending_rule = "resolve:" + bindings.final_decision_id
        compiled.append(
            Rule(
                rule_id=ending_rule,
                priority=max((rule.priority for rule in compiled), default=0) + 100,
                event="option_chosen",
                target_id=bindings.final_decision_id,
                guard=AnyOf(
                    kind="any",
                    conditions=tuple(
                        ChoiceEquals(
                            kind="choice_equals",
                            decision_id=bindings.final_decision_id,
                            option_id=option.option_id,
                        )
                        for option in decisions[bindings.final_decision_id].options
                    ),
                ),
                effects=(
                    ResolveEnding(kind="resolve_ending", ending_table_id=bindings.ending_table_id),
                ),
                once_key=ending_rule,
            )
        )
        scenes_by_task = {task.task_id: scene for scene in game.scenes for task in scene.tasks}
        reports = tuple(
            updated(
                report,
                effect_ids=tuple(
                    dict.fromkeys(
                        (
                            *([task_rules[report.task_id]] if report.task_id in task_rules else []),
                            *(
                                binding.source_rule_id
                                for binding in bindings.choices
                                if binding.decision_id == scenes_by_task[report.task_id].decision_id
                            ),
                            *(
                                [ending_rule]
                                if scenes_by_task[report.task_id].decision_id
                                == bindings.final_decision_id
                                else []
                            ),
                        )
                    )
                ),
            )
            for report in draft.authoring_report
        )
        return updated(
            draft,
            package=updated(draft.package, game=updated(game, rules=tuple(compiled))),
            authoring_report=reports,
        )
