"""Compile an explicitly bounded story plan into the existing executable contract."""

import json

from pastport.domain.common import CanonicalSerializer, Locale
from pastport.domain.game import (
    All,
    Character,
    ChoiceEquals,
    Decision,
    Ending,
    EndingTable,
    GameContent,
    InitialState,
    InspectTask,
    LocaleTable,
    NarrativePackage,
    ObservedAll,
    Option,
    Outcome,
    ResolveEnding,
    Rule,
    Scene,
    SetVariable,
    Spot,
    Translation,
    UnlockScene,
    Variable,
    VariableEquals,
)
from pastport.domain.modules import (
    AuthoringTaskReport,
    DraftRequest,
    NarrativeDraft,
    TaskGameplayIntent,
    TaskReadingIntent,
    TaskSpatialIntent,
    TaskTilingIntent,
)
from pastport.domain.story_plan import BranchStoryPlan, StoryPlan, StoryPlanTask, StoryText


class StoryPlanCompiler:
    """Own all runtime IDs, state declarations, locale keys and graph references.

    v1 is ordered one-task scenes with one final choice. It does not claim to
    compile arbitrary branching graphs or infer missing gameplay semantics.
    """

    def compile(self, plan: StoryPlan | BranchStoryPlan, request: DraftRequest) -> NarrativeDraft:
        if isinstance(plan, BranchStoryPlan):
            from pastport.application.story_branch_compiler import BranchStoryPlanCompiler

            return BranchStoryPlanCompiler().compile(plan, request)
        return self.compile_ordered(plan, plan.tasks, request)

    def compile_saved_revision(
        self,
        plan: StoryPlan | BranchStoryPlan,
        previous: NarrativeDraft,
    ) -> NarrativeDraft:
        """Recompile a human-edited plan using only a saved draft's registered selections.

        Preserves provenance and unresolved items; this is not new model generation
        or an evidence/review approval. New object/claim/view bindings need upstream work.
        """
        if plan.capability_catalog_sha256 != previous.capability_catalog_sha256:
            raise ValueError("Saved revision changed the pinned gameplay capability catalog")
        tasks = (
            plan.tasks
            if isinstance(plan, StoryPlan)
            else (
                *plan.opening,
                *(task for route in plan.investigations for task in route.tasks),
                *plan.reunion,
            )
        )
        intents = {item.task_id: item for item in previous.spatial_intents}
        known = [
            (task, intents[task.task_id], scene.site_id)
            for scene in previous.package.game.scenes
            for task in scene.tasks
            if task.task_id in intents and isinstance(task, InspectTask)
        ]
        site = previous.package.game.scenes[0].site_id
        for task in tasks:
            if not any(
                old.asset_id == task.asset_id
                and intent.view_id == task.view_id
                and intent.station_id == "spawn"
                and intent.interaction == "inspect_linked_source"
                and set(task.claim_ids) <= set(old.evidence_refs)
                and old_site == site
                for old, intent, old_site in known
            ):
                raise ValueError("Saved revision introduced an unregistered asset/claim/view/site")
        if isinstance(plan, BranchStoryPlan):
            from pastport.application.story_branch_compiler import BranchStoryPlanCompiler

            draft = BranchStoryPlanCompiler().compile(plan, previous)
        else:
            draft = self.compile_ordered(plan, plan.tasks, previous)
        from pastport.application.updates import updated

        return updated(
            draft,
            unresolved_items=tuple(
                dict.fromkeys(
                    (
                        *previous.unresolved_items,
                        *draft.unresolved_items,
                        "Human-edited saved-plan revision; "
                        "not a fresh model generation or source approval.",
                    )
                )
            ),
        )

    def compile_ordered(
        self,
        plan: StoryPlan | BranchStoryPlan,
        tasks: tuple[StoryPlanTask, ...],
        request: DraftRequest | NarrativeDraft,
    ) -> NarrativeDraft:
        """Shared content compilation; callers must validate their final graph."""
        translations: dict[str, StoryText] = {}
        secondary = "tr" if plan.protagonist_name.tr is not None else "zh"

        def text(key: str, value: StoryText) -> str:
            if key in translations:
                raise ValueError("Compiler locale key collision")
            translations[key] = value
            return key

        character = Character(
            character_id="protagonist",
            name_key=text("protagonist.name", plan.protagonist_name),
            goal_key=text("protagonist.goal", plan.protagonist_goal),
        )
        scenes: list[Scene] = []
        rules: list[Rule] = []
        reports: list[AuthoringTaskReport] = []
        spatial: list[TaskSpatialIntent] = []
        gameplay: list[TaskGameplayIntent] = []
        site = (
            request.evidence.route.ordered_places[0].site_id
            if isinstance(request, DraftRequest)
            else request.package.game.scenes[0].site_id
        )
        size = len(tasks)
        for number, task in enumerate(tasks, 1):
            scene_id, task_id, rule_id = f"scene-{number}", f"task-{number}", f"task-rule-{number}"
            last = number == size
            next_scene = scene_id if last else f"scene-{number + 1}"
            inspect = InspectTask(
                kind="inspect",
                task_id=task_id,
                objective_key=text(task_id + ".objective", task.objective),
                prerequisite_task_ids=(),
                guard=None,
                evidence_refs=task.claim_ids,
                character_goal_link="protagonist",
                feedback_key=text(task_id + ".feedback", task.feedback),
                hint_keys=tuple(
                    text(f"{task_id}.hint-{n}", hint) for n, hint in enumerate(task.hints)
                ),
                accessibility_key=text(task_id + ".accessibility", task.accessibility),
                asset_id=task.asset_id,
                spots=(
                    Spot(
                        spot_id="result",
                        x=5000,
                        y=5000,
                        text_key=text(task_id + ".source", task.objective),
                        claim_ids=task.claim_ids,
                    ),
                ),
                required_spot_ids=("result",),
            )
            scenes.append(
                Scene(
                    scene_id=scene_id,
                    site_id=site,
                    title_key=text(scene_id + ".title", task.title),
                    body_key=text(scene_id + ".body", task.dialogue),
                    tasks=(inspect,),
                    required_task_ids=(task_id,),
                    decision_id="final-choice" if last else None,
                    next_scene_ids=() if last else (next_scene,),
                    feedback=(),
                )
            )
            # State is program-owned, not a list of model-authored variable writes.
            effect: UnlockScene | SetVariable = (
                SetVariable(kind="set_variable", name="final-task-complete", value=True)
                if last
                else UnlockScene(kind="unlock_scene", scene_id=next_scene)
            )
            rules.append(
                Rule(
                    rule_id=rule_id,
                    priority=number,
                    event="task_completed",
                    target_id=task_id,
                    guard=ObservedAll(kind="observed_all", scene_id=scene_id, spot_ids=("result",)),
                    effects=(effect,),
                    once_key="once:" + rule_id,
                )
            )
            object_number = int(task.asset_id.removeprefix("object-"))
            spatial.append(
                TaskSpatialIntent(
                    task_id=task_id,
                    object_number=object_number,
                    view_id=task.view_id,
                    station_id="spawn",
                    interaction="inspect_linked_source",
                )
            )
            if task.gameplay.kind == "source_reading":
                gameplay.append(TaskReadingIntent(task_id=task_id))
            else:
                gameplay.append(TaskTilingIntent(task_id=task_id, **task.gameplay.model_dump()))
            reports.append(
                AuthoringTaskReport(
                    task_id=task_id,
                    player_action_id=task_id,
                    heritage_refs=task.claim_ids,
                    premise_source_ids=task.claim_ids,
                    character_goal="protagonist",
                    effect_ids=(rule_id,),
                    consequence_read_scene_id=next_scene,
                    observable_feedback=task.feedback.localized(secondary),
                    **task.reasoning.model_dump(),
                )
            )
        options: list[Option] = []
        endings: list[Ending] = []
        for number, choice in enumerate(plan.choices, 1):
            option_id, ending_id = f"option-{number}", f"ending-{number}"
            options.append(
                Option(option_id=option_id, text_key=text(option_id + ".label", choice.label))
            )
            rule_id = "choice-rule-" + str(number)
            rules.append(
                Rule(
                    rule_id=rule_id,
                    priority=size + number,
                    event="option_chosen",
                    target_id="final-choice",
                    guard=All(
                        kind="all",
                        conditions=(
                            VariableEquals(
                                kind="variable_equals", name="final-task-complete", value=True
                            ),
                            ChoiceEquals(
                                kind="choice_equals",
                                decision_id="final-choice",
                                option_id=option_id,
                            ),
                        ),
                    ),
                    effects=(
                        SetVariable(kind="set_variable", name="ending-choice", value=number),
                        ResolveEnding(kind="resolve_ending", ending_table_id="final-endings"),
                    ),
                    once_key="once:" + rule_id,
                )
            )
            fallback = number == len(plan.choices)
            endings.append(
                Ending(
                    ending_id=ending_id,
                    priority=number,
                    guard=None
                    if fallback
                    else VariableEquals(kind="variable_equals", name="ending-choice", value=number),
                    fallback=fallback,
                    outcomes=(
                        Outcome(
                            outcome_id=ending_id + ".outcome",
                            label_key=text(ending_id + ".label", choice.label),
                            text_key=text(ending_id + ".consequence", choice.consequence),
                            variants=(),
                        ),
                    ),
                )
            )
        # Store display-only copy in compiler-owned locale keys. The NarrativeDraft
        # wire shape and old plans without opening_context stay unchanged.
        opening = plan.opening_context
        if opening is not None:
            text(
                "presentation.opening_v1", StoryText(en="opening-context/1", **{secondary: "opening-context/1"})
            )
            for key, value in (
                ("title", opening.title),
                ("setting", opening.setting),
                ("situation", opening.situation),
                ("player_role", opening.player_role),
                ("question", opening.central_question),
            ):
                text("presentation." + key, value)
            for index, person in enumerate(opening.people, 1):
                prefix = f"presentation.person.{index}."
                text(prefix + "name", person.name)
                text(prefix + "introduction", person.introduction)
            for station in opening.stations:
                prefix = f"presentation.station.{station.asset_id}."
                text(prefix + "title", station.title)
                documents = [material for material in plan.fictional_materials if any(
                    tasks[position - 1].asset_id == station.asset_id
                    for position in material.task_positions
                )]
                if documents:
                    purpose = StoryText(**{
                        locale: station.purpose.localized(locale) + "\n\n" + "\n\n".join(
                            ("虚构材料改编" if locale == "zh" else "Uyarlanmış kurgu" if locale == "tr" else "Adapted fictional material")
                            + f" · {material.section_id} / {material.material_id}\n"
                            + material.title.localized(locale) + "\n" + material.body.localized(locale)
                            for material in documents
                        ) for locale in ("en", secondary)
                    })
                else:
                    purpose = station.purpose
                text(prefix + "purpose", purpose)

        design = plan.activity_design
        if design is not None:
            blueprint = design.model_dump(mode="json", exclude_none=True)
            blueprint["schema_version"] = "investigation-blueprint/1"
            blueprint["package_id"] = (
                "story-investigation-" + CanonicalSerializer.digest(design)[:16]
            )
            anchors: dict[int, str] = {}
            for index, row in enumerate(blueprint["interludes"], 1):
                anchor = row.pop("after_task")
                row["after_scene_id"] = anchors.get(anchor, f"scene-{anchor}")
                row["scene_id"] = f"investigation-scene-{index}"
                row["task_id"] = f"investigation-task-{index}"
                anchors[anchor] = row["scene_id"]
                if "reward" in row:
                    row["reward"] = {"id": f"investigation-reward-{index}", "text": row["reward"]}
            encoded = json.dumps(
                blueprint, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            )
            chunks = [encoded[start : start + 8000] for start in range(0, len(encoded), 8000)]
            text(
                "preparation.investigation_v1",
                StoryText(en="investigation-blueprint/1", **{secondary: "investigation-blueprint/1"}),
            )
            text(
                "preparation.investigation_parts",
                StoryText(en=str(len(chunks)), **{secondary: str(len(chunks))}),
            )
            for index, chunk in enumerate(chunks, 1):
                text(f"preparation.investigation_part.{index}", StoryText(en=chunk, **{secondary: chunk}))

        locales: tuple[Locale, ...] = ("en", "tr" if secondary == "tr" else "zh")
        game = GameContent(
            chapter_id="chapter-1",
            protagonist="protagonist",
            characters=(character,),
            scenes=tuple(scenes),
            props=(),
            decisions=(Decision(decision_id="final-choice", options=tuple(options)),),
            variables=(
                Variable(name="final-task-complete", initial=False),
                Variable(name="ending-choice", initial=0),
            ),
            rules=tuple(rules),
            endings=(EndingTable(ending_table_id="final-endings", endings=tuple(endings)),),
            initial_state=InitialState(
                current_scene_id="scene-1",
                inventory=(),
                unlocked_scene_ids=("scene-1",),
                elapsed_minutes=0,
            ),
            locales=tuple(
                LocaleTable(
                    locale=locale,
                    entries=tuple(
                        Translation(key=key, text=value.localized(locale))
                        for key, value in translations.items()
                    ),
                )
                for locale in locales
            ),
        )
        package = NarrativePackage(
            schema_version="0.1.0",
            content_version="compiled-plan-v1",
            project_id=(
                request.selected_candidate.project_id
                if isinstance(request, DraftRequest)
                else request.package.project_id
            ),
            evidence_package_hash=(
                request.evidence.evidence_ref.sha256
                if isinstance(request, DraftRequest)
                else request.package.evidence_package_hash
            ),
            candidate_id=(
                request.selected_candidate.candidate_id
                if isinstance(request, DraftRequest)
                else request.package.candidate_id
            ),
            routes=(
                (request.evidence.approved_route_ref,)
                if isinstance(request, DraftRequest)
                else request.package.routes
            ),
            game=game,
            fiction_notice=plan.fiction_notice,
        )
        return NarrativeDraft(
            package=package,
            spatial_intents=tuple(spatial),
            gameplay_intents=tuple(gameplay),
            capability_catalog_sha256=plan.capability_catalog_sha256,
            authoring_report=tuple(reports),
            unresolved_items=plan.unresolved_items,
        )
