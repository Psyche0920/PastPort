"""Compile exclusive investigation routes into the shared game rules, without new engine code."""

from pastport.application.story_compiler import StoryPlanCompiler
from pastport.application.updates import updated
from pastport.domain.game import (
    All,
    ChoiceEquals,
    Decision,
    Effect,
    Feedback,
    GrantItem,
    LocaleTable,
    Option,
    OutcomeVariant,
    Prop,
    Rule,
    SetVariable,
    Translation,
    UnlockScene,
    Variable,
    VariableEquals,
)
from pastport.domain.modules import DraftRequest, NarrativeDraft
from pastport.domain.story_plan import BranchStoryPlan, StoryText


class BranchStoryPlanCompiler:
    """One bounded fork and reunion; completion grants one persistent fictional finding."""

    def compile(
        self,
        plan: BranchStoryPlan,
        request: DraftRequest | NarrativeDraft,
    ) -> NarrativeDraft:
        tasks = (
            *plan.opening,
            *(task for route in plan.investigations for task in route.tasks),
            *plan.reunion,
        )
        draft = StoryPlanCompiler().compile_ordered(plan, tasks, request)
        game = draft.package.game
        tables: dict[str, dict[str, str]] = {
            table.locale: {item.key: item.text for item in table.entries} for table in game.locales
        }

        def text(key: str, value: StoryText) -> str:
            for locale, table in tables.items():
                if key in table:
                    raise ValueError("Compiler locale key collision")
                table[key] = value.en if locale == "en" else value.zh
            return key

        pivot = len(plan.opening)
        reunion = len(tasks) - len(plan.reunion) + 1
        starts: list[int] = []
        ends: list[int] = []
        cursor = pivot + 1
        for route in plan.investigations:
            starts.append(cursor)
            cursor += len(route.tasks)
            ends.append(cursor - 1)
        scenes = list(game.scenes)
        scenes[pivot - 1] = updated(
            scenes[pivot - 1],
            decision_id="investigation-choice",
            next_scene_ids=tuple(f"scene-{n}" for n in starts),
        )
        rules = list(game.rules)
        reports = list(draft.authoring_report)
        # Complete the opening before permitting the route choice. Never unlock all routes.
        rules[pivot - 1] = updated(
            rules[pivot - 1],
            effects=(SetVariable(kind="set_variable", name="investigation-ready", value=True),),
        )
        options: list[Option] = []
        props: list[Prop] = []
        feedback: list[Feedback] = []
        variants: list[list[OutcomeVariant]] = [[] for _ in plan.choices]
        for number, (route, start, end) in enumerate(
            zip(plan.investigations, starts, ends, strict=True), 1
        ):
            option_id = f"investigation-{number}"
            options.append(
                Option(option_id=option_id, text_key=text(option_id + ".label", route.label))
            )
            rule_id = option_id + "-chosen"
            rules.append(
                Rule(
                    rule_id=rule_id,
                    priority=len(tasks) + len(plan.choices) + number,
                    event="option_chosen",
                    target_id="investigation-choice",
                    guard=All(
                        kind="all",
                        conditions=(
                            VariableEquals(
                                kind="variable_equals", name="investigation-ready", value=True
                            ),
                            ChoiceEquals(
                                kind="choice_equals",
                                decision_id="investigation-choice",
                                option_id=option_id,
                            ),
                        ),
                    ),
                    effects=(
                        SetVariable(kind="set_variable", name="investigation", value=number),
                        UnlockScene(kind="unlock_scene", scene_id=f"scene-{start}"),
                    ),
                    once_key="once:" + rule_id,
                )
            )
            finding_id = f"finding-{number}"
            props.append(
                Prop(
                    prop_id=finding_id,
                    text_key=text(finding_id + ".text", route.finding),
                    content_kind="original_fiction",
                )
            )
            scenes[end - 1] = updated(scenes[end - 1], next_scene_ids=(f"scene-{reunion}",))
            completion = rules[end - 1]
            effects: tuple[Effect, ...] = (
                SetVariable(kind="set_variable", name="investigation-complete", value=number),
                GrantItem(kind="grant_item", item_id=finding_id),
                UnlockScene(kind="unlock_scene", scene_id=f"scene-{reunion}"),
            )
            rules[end - 1] = updated(completion, effects=effects)
            reports[end - 1] = updated(
                reports[end - 1], consequence_read_scene_id=f"scene-{reunion}"
            )
            guard = VariableEquals(
                kind="variable_equals", name="investigation-complete", value=number
            )
            feedback.append(
                Feedback(
                    feedback_id=option_id + "-reunion",
                    guard=guard,
                    text_key=text(option_id + ".reunion", route.reunion_feedback),
                )
            )
            for index, consequence in enumerate(route.ending_consequences):
                key = f"ending-{index + 1}.{option_id}"
                variants[index].append(
                    OutcomeVariant(
                        variant_id=key,
                        priority=number,
                        guard=guard,
                        text_key=text(key + ".text", consequence),
                    )
                )
        scenes[reunion - 1] = updated(scenes[reunion - 1], feedback=tuple(feedback))
        # A report may point to one declared downstream consequence; the full fork
        # is represented by the decision rules and route-specific reunion feedback.
        reports[pivot - 1] = updated(
            reports[pivot - 1], consequence_read_scene_id=f"scene-{reunion}"
        )
        table = game.endings[0]
        endings = tuple(
            updated(
                ending,
                outcomes=tuple(
                    updated(outcome, variants=tuple(variants[index])) for outcome in ending.outcomes
                ),
            )
            for index, ending in enumerate(table.endings)
        )
        compiled = updated(
            game,
            scenes=tuple(scenes),
            rules=tuple(rules),
            props=tuple(props),
            decisions=(
                *game.decisions,
                Decision(decision_id="investigation-choice", options=tuple(options)),
            ),
            variables=(
                *game.variables,
                Variable(name="investigation-ready", initial=False),
                Variable(name="investigation", initial=0),
                Variable(name="investigation-complete", initial=0),
            ),
            endings=(updated(table, endings=endings),),
            locales=tuple(
                LocaleTable(
                    locale=table.locale,
                    entries=tuple(
                        Translation(key=key, text=value)
                        for key, value in tables[table.locale].items()
                    ),
                )
                for table in game.locales
            ),
        )
        return updated(
            draft,
            package=updated(draft.package, game=compiled, content_version="compiled-branch-v1"),
            authoring_report=tuple(reports),
        )
