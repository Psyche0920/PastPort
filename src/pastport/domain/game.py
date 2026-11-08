"""Bounded, declarative game data. This module does not interpret actions."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import (
    ArtifactRef,
    Contract,
    Identifier,
    Locale,
    NonNegative,
    Positive,
    Sha256,
    Text,
    Version,
    VersionedPayload,
    unique,
)

SafeInteger = Annotated[int, Field(ge=-9007199254740991, le=9007199254740991)]
Scalar = bool | SafeInteger | Annotated[str, Field(max_length=10000)]


class ObservedAll(Contract):
    kind: Literal["observed_all"]
    scene_id: Identifier
    spot_ids: tuple[Identifier, ...] = Field(min_length=1)


class ChoiceEquals(Contract):
    kind: Literal["choice_equals"]
    decision_id: Identifier
    option_id: Identifier


class VariableEquals(Contract):
    kind: Literal["variable_equals"]
    name: Identifier
    value: Scalar


class HasEvidence(Contract):
    kind: Literal["has_evidence"]
    item_id: Identifier


class ElapsedGt(Contract):
    kind: Literal["elapsed_gt"]
    minutes: NonNegative


class All(Contract):
    kind: Literal["all"]
    conditions: tuple["Condition", ...] = Field(min_length=1, max_length=32)


class AnyOf(Contract):
    kind: Literal["any"]
    conditions: tuple["Condition", ...] = Field(min_length=1, max_length=32)


class Not(Contract):
    kind: Literal["not"]
    condition: "Condition"


Condition = Annotated[
    ObservedAll | ChoiceEquals | VariableEquals | HasEvidence | ElapsedGt | All | AnyOf | Not,
    Field(discriminator="kind"),
]


class GrantItem(Contract):
    kind: Literal["grant_item"]
    item_id: Identifier


class SetVariable(Contract):
    kind: Literal["set_variable", "set_relationship"]
    name: Identifier
    value: Scalar


class AddStoryTime(Contract):
    kind: Literal["add_story_time"]
    minutes: NonNegative


class UnlockScene(Contract):
    kind: Literal["unlock_scene"]
    scene_id: Identifier


class ResolveEnding(Contract):
    kind: Literal["resolve_ending"]
    ending_table_id: Identifier


Effect = Annotated[
    GrantItem | SetVariable | AddStoryTime | UnlockScene | ResolveEnding,
    Field(discriminator="kind"),
]
EventKind = Literal["spot_observed", "board_submitted", "option_chosen", "task_completed"]


class Rule(Contract):
    rule_id: Identifier
    priority: NonNegative
    event: EventKind
    target_id: Identifier
    guard: Condition
    effects: tuple[Effect, ...] = Field(min_length=1, max_length=32)
    once_key: Identifier


class Spot(Contract):
    spot_id: Identifier
    x: Annotated[int, Field(ge=0, le=10000)]
    y: Annotated[int, Field(ge=0, le=10000)]
    text_key: Identifier
    claim_ids: tuple[Identifier, ...] = Field(min_length=1)


class TaskBase(Contract):
    task_id: Identifier
    objective_key: Identifier
    prerequisite_task_ids: tuple[Identifier, ...]
    guard: Condition | None
    evidence_refs: tuple[Identifier, ...] = Field(min_length=1)
    character_goal_link: Identifier
    feedback_key: Identifier
    hint_keys: tuple[Identifier, ...]
    accessibility_key: Identifier


class InspectTask(TaskBase):
    kind: Literal["inspect"]
    asset_id: Identifier
    spots: tuple[Spot, ...] = Field(min_length=1)
    required_spot_ids: tuple[Identifier, ...] = Field(min_length=1)


class CaseboardTask(TaskBase):
    kind: Literal["caseboard"]
    required_prop_ids: tuple[Identifier, ...] = Field(min_length=1)
    answer_rule: Literal["exact_set"]


Task = Annotated[InspectTask | CaseboardTask, Field(discriminator="kind")]


class Option(Contract):
    option_id: Identifier
    text_key: Identifier


class Decision(Contract):
    decision_id: Identifier
    options: tuple[Option, ...] = Field(min_length=2)


class Scene(Contract):
    scene_id: Identifier
    site_id: Identifier
    title_key: Identifier
    body_key: Identifier
    tasks: tuple[Task, ...] = Field(min_length=1, max_length=1)
    required_task_ids: tuple[Identifier, ...] = Field(min_length=1)
    decision_id: Identifier | None
    next_scene_ids: tuple[Identifier, ...]
    feedback: tuple["Feedback", ...]


class Feedback(Contract):
    feedback_id: Identifier
    guard: Condition
    text_key: Identifier


class Prop(Contract):
    prop_id: Identifier
    text_key: Identifier
    content_kind: Literal["original_fiction"]


class Character(Contract):
    character_id: Identifier
    name_key: Identifier
    goal_key: Identifier


class Variable(Contract):
    name: Identifier
    initial: Scalar


class Translation(Contract):
    key: Identifier
    text: Text


class LocaleTable(Contract):
    locale: Locale
    entries: tuple[Translation, ...] = Field(min_length=1)


class OutcomeVariant(Contract):
    variant_id: Identifier
    priority: NonNegative
    guard: Condition
    text_key: Identifier


class Outcome(Contract):
    outcome_id: Identifier
    label_key: Identifier
    text_key: Identifier
    variants: tuple[OutcomeVariant, ...]


class Ending(Contract):
    ending_id: Identifier
    priority: NonNegative
    guard: Condition | None
    fallback: bool
    outcomes: tuple[Outcome, ...] = Field(min_length=1)


class EndingTable(Contract):
    ending_table_id: Identifier
    endings: tuple[Ending, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def fallback_last(self) -> Self:
        unique((x.ending_id for x in self.endings), "ending IDs")
        fallback = [x for x in self.endings if x.fallback]
        if len(fallback) != 1 or fallback[0].guard is not None:
            raise ValueError("Exactly one unconditional fallback is required")
        if any(x.guard is None for x in self.endings if not x.fallback):
            raise ValueError("Non-fallback endings require guards")
        if any(x.priority >= fallback[0].priority for x in self.endings if not x.fallback):
            raise ValueError("Fallback must have a strictly greater priority")
        return self


class InitialState(Contract):
    current_scene_id: Identifier
    inventory: tuple[Identifier, ...]
    unlocked_scene_ids: tuple[Identifier, ...] = Field(min_length=1)
    elapsed_minutes: NonNegative


class RuntimeCapabilities(Contract):
    profile: Literal["t1a-single-task"]
    contract_version: Version
    task_kinds: tuple[Literal["inspect", "caseboard"], ...]
    condition_kinds: tuple[
        Literal[
            "all",
            "any",
            "not",
            "observed_all",
            "choice_equals",
            "variable_equals",
            "has_evidence",
            "elapsed_gt",
        ],
        ...,
    ]
    effect_kinds: tuple[
        Literal[
            "grant_item",
            "set_variable",
            "set_relationship",
            "add_story_time",
            "unlock_scene",
            "resolve_ending",
        ],
        ...,
    ]
    event_kinds: tuple[EventKind, ...]
    locales: tuple[Locale, ...]
    max_events_per_action: Positive = 2
    max_effects_per_action: Positive = 64
    max_condition_depth: Positive = 8

    @model_validator(mode="after")
    def complete_profile(self) -> Self:
        expected = {
            "task_kinds": {"inspect", "caseboard"},
            "condition_kinds": {
                "all",
                "any",
                "not",
                "observed_all",
                "choice_equals",
                "variable_equals",
                "has_evidence",
                "elapsed_gt",
            },
            "effect_kinds": {
                "grant_item",
                "set_variable",
                "set_relationship",
                "add_story_time",
                "unlock_scene",
                "resolve_ending",
            },
            "event_kinds": {"spot_observed", "board_submitted", "option_chosen", "task_completed"},
            "locales": {"en", "zh"},
        }
        for name, values in expected.items():
            actual = getattr(self, name)
            if name == "locales" and set(actual) == {"en", "tr"} and len(actual) == 2:
                continue
            if set(actual) != values or len(actual) != len(values):
                raise ValueError(f"Profile capability mismatch: {name}")
        if (self.max_events_per_action, self.max_effects_per_action, self.max_condition_depth) != (
            2,
            64,
            8,
        ):
            raise ValueError("Profile execution limits are fixed")
        return self


class GameContent(Contract):
    chapter_id: Identifier
    protagonist: Identifier
    characters: tuple[Character, ...] = Field(min_length=1)
    scenes: tuple[Scene, ...] = Field(min_length=1, max_length=64)
    props: tuple[Prop, ...]
    decisions: tuple[Decision, ...]
    variables: tuple[Variable, ...]
    rules: tuple[Rule, ...]
    endings: tuple[EndingTable, ...]
    initial_state: InitialState
    locales: tuple[LocaleTable, ...]

    @model_validator(mode="after")
    def references(self) -> Self:
        # All reference identities are validated here; reachability remains a T6 check.
        groups = {
            "scene": tuple(x.scene_id for x in self.scenes),
            "task": tuple(x.task_id for s in self.scenes for x in s.tasks),
            "prop": tuple(x.prop_id for x in self.props),
            "decision": tuple(x.decision_id for x in self.decisions),
            "variable": tuple(x.name for x in self.variables),
            "character": tuple(x.character_id for x in self.characters),
            "ending_table": tuple(x.ending_table_id for x in self.endings),
            "rule": tuple(x.rule_id for x in self.rules),
            "once": tuple(x.once_key for x in self.rules),
        }
        for name, ids in groups.items():
            unique(ids, name)
        self.require_id(self.protagonist, groups["character"])
        self.require_id(self.initial_state.current_scene_id, self.initial_state.unlocked_scene_ids)
        for value in self.initial_state.unlocked_scene_ids:
            self.require_id(value, groups["scene"])
        for value in self.initial_state.inventory:
            self.require_id(value, groups["prop"])
        unique(self.initial_state.inventory, "initial inventory")
        unique(self.initial_state.unlocked_scene_ids, "initial unlocks")
        unique(
            (x.decision_id for x in self.scenes if x.decision_id is not None),
            "scene decisions",
        )
        keys: set[str] = set()
        for character in self.characters:
            keys.update((character.name_key, character.goal_key))
        keys.update(x.text_key for x in self.props)
        for scene in self.scenes:
            keys.update((scene.title_key, scene.body_key))
            unique(scene.next_scene_ids, "next scenes")
            for next_id in scene.next_scene_ids:
                self.require_id(next_id, groups["scene"])
            if scene.decision_id is not None:
                self.require_id(scene.decision_id, groups["decision"])
            local_tasks = tuple(x.task_id for x in scene.tasks)
            unique(scene.required_task_ids, "required tasks")
            for task_id in scene.required_task_ids:
                self.require_id(task_id, local_tasks)
            for task in scene.tasks:
                # This profile intentionally excludes multi-task dependencies.
                if task.prerequisite_task_ids:
                    raise ValueError("Task dependencies require a later capability profile")
                self.require_id(task.character_goal_link, groups["character"])
                keys.update(
                    (task.objective_key, task.feedback_key, task.accessibility_key, *task.hint_keys)
                )
                if task.guard:
                    self.check_condition(task.guard)
                if isinstance(task, InspectTask):
                    unique((x.spot_id for x in task.spots), "spots")
                    unique(task.required_spot_ids, "required spots")
                    for spot_id in task.required_spot_ids:
                        self.require_id(spot_id, tuple(x.spot_id for x in task.spots))
                    keys.update(x.text_key for x in task.spots)
                else:
                    unique(task.required_prop_ids, "required props")
                    for prop_id in task.required_prop_ids:
                        self.require_id(prop_id, groups["prop"])
            for feedback in scene.feedback:
                keys.add(feedback.text_key)
                self.check_condition(feedback.guard)
        for decision in self.decisions:
            unique((x.option_id for x in decision.options), "options")
            keys.update(x.text_key for x in decision.options)
        for rule in self.rules:
            targets = groups["decision"] if rule.event == "option_chosen" else groups["task"]
            self.require_id(rule.target_id, targets)
            if rule.event in ("spot_observed", "board_submitted"):
                target_task = next(
                    task
                    for scene in self.scenes
                    for task in scene.tasks
                    if task.task_id == rule.target_id
                )
                expected_kind = "inspect" if rule.event == "spot_observed" else "caseboard"
                if target_task.kind != expected_kind:
                    raise ValueError("Event does not match its task handler")
            self.check_condition(rule.guard)
            for effect in rule.effects:
                if isinstance(effect, GrantItem):
                    self.require_id(effect.item_id, groups["prop"])
                elif isinstance(effect, UnlockScene):
                    self.require_id(effect.scene_id, groups["scene"])
                elif isinstance(effect, SetVariable):
                    self.check_variable(effect.name, effect.value)
                    if effect.kind == "set_relationship" and type(effect.value) is not str:
                        raise ValueError("Relationships require a string variable")
                elif isinstance(effect, ResolveEnding):
                    self.require_id(effect.ending_table_id, groups["ending_table"])
        for table in self.endings:
            for ending in table.endings:
                if ending.guard:
                    self.check_condition(ending.guard)
                unique((x.outcome_id for x in ending.outcomes), "outcomes")
                for outcome in ending.outcomes:
                    keys.update((outcome.label_key, outcome.text_key))
                    unique((x.variant_id for x in outcome.variants), "variants")
                    for variant in outcome.variants:
                        keys.add(variant.text_key)
                        self.check_condition(variant.guard)
        unique((x.locale for x in self.locales), "locales")
        if {x.locale for x in self.locales} not in ({"en", "zh"}, {"en", "tr"}):
            raise ValueError("Both locales are required")
        key_sets = []
        for locale in self.locales:
            unique((x.key for x in locale.entries), "locale keys")
            present = {x.key for x in locale.entries}
            if not keys <= present:
                raise ValueError("Missing locale keys")
            key_sets.append(present)
        if key_sets[0] != key_sets[1]:
            raise ValueError("Locale key sets must agree")
        return self

    @staticmethod
    def require_id(value: str, available: tuple[str, ...]) -> None:
        if value not in available:
            raise ValueError(f"Unknown reference: {value}")

    def check_variable(self, name: str, value: Scalar) -> None:
        variable = next((x for x in self.variables if x.name == name), None)
        if variable is None or type(variable.initial) is not type(value):
            raise ValueError("Unknown variable or mismatched scalar type")

    def check_condition(self, condition: Condition, depth: int = 1) -> None:
        if depth > 8:
            raise ValueError("Condition depth exceeds profile limit")
        if isinstance(condition, All | AnyOf):
            for child in condition.conditions:
                self.check_condition(child, depth + 1)
        elif isinstance(condition, Not):
            self.check_condition(condition.condition, depth + 1)
        elif isinstance(condition, ObservedAll):
            scene = next((x for x in self.scenes if x.scene_id == condition.scene_id), None)
            if scene is None or not isinstance(scene.tasks[0], InspectTask):
                raise ValueError("Observation must reference an inspect scene")
            unique(condition.spot_ids, "condition spots")
            for spot_id in condition.spot_ids:
                self.require_id(spot_id, tuple(x.spot_id for x in scene.tasks[0].spots))
        elif isinstance(condition, ChoiceEquals):
            decision = next(
                (x for x in self.decisions if x.decision_id == condition.decision_id), None
            )
            if decision is None:
                raise ValueError("Unknown decision")
            self.require_id(condition.option_id, tuple(x.option_id for x in decision.options))
        elif isinstance(condition, VariableEquals):
            self.check_variable(condition.name, condition.value)
        elif isinstance(condition, HasEvidence):
            self.require_id(condition.item_id, tuple(x.prop_id for x in self.props))


class ObservationSet(Contract):
    scene_id: Identifier
    spot_ids: tuple[Identifier, ...]


class ChoiceState(Contract):
    decision_id: Identifier
    option_id: Identifier


class VariableState(Contract):
    name: Identifier
    value: Scalar


class Assignment(Contract):
    task_id: Identifier
    pairs: tuple["AssignmentPair", ...]


class AssignmentPair(Contract):
    card_id: Identifier
    destination_id: Identifier


class EvidenceSelection(Contract):
    task_id: Identifier
    prop_ids: tuple[Identifier, ...]


class GameEvent(Contract):
    event_id: Identifier
    kind: EventKind
    target_id: Identifier


class ActionReceipt(Contract):
    action_id: Identifier
    payload_hash: Sha256
    feedback_keys: tuple[Identifier, ...]
    event_ids: tuple[Identifier, ...]


class PlayerState(Contract):
    project_id: Identifier
    release_id: Identifier
    package_hash: Sha256
    chapter_id: Identifier
    schema_version: Version
    revision: NonNegative
    current_scene_id: Identifier
    elapsed_minutes: NonNegative
    observations: tuple[ObservationSet, ...]
    completed_task_ids: tuple[Identifier, ...]
    decisions: tuple[ChoiceState, ...]
    inventory: tuple[Identifier, ...]
    assignments: tuple[Assignment, ...]
    selected_evidence: tuple[EvidenceSelection, ...]
    variables: tuple[VariableState, ...]
    unlocked_scene_ids: tuple[Identifier, ...]
    applied_rule_keys: tuple[Identifier, ...]
    processed_actions: tuple[ActionReceipt, ...]
    ending_id: Identifier | None


class ActionBase(Contract):
    action_id: Identifier
    expected_revision: NonNegative
    target_id: Identifier


class Observe(ActionBase):
    kind: Literal["observe"]
    spot_id: Identifier


class Choose(ActionBase):
    kind: Literal["choose"]
    option_id: Identifier


class SubmitEvidence(ActionBase):
    kind: Literal["submit_evidence"]
    prop_ids: tuple[Identifier, ...] = Field(min_length=1)


class Advance(ActionBase):
    kind: Literal["advance"]


Action = Annotated[Observe | Choose | SubmitEvidence | Advance, Field(discriminator="kind")]


class ActionRequest(Contract):
    project_id: Identifier
    release_id: Identifier
    package_hash: Sha256
    action: Action


class RuleTrace(Contract):
    event_id: Identifier
    rule_id: Identifier
    effects: tuple[Effect, ...]


class ActionResult(Contract):
    state: PlayerState
    emitted_events: tuple[GameEvent, ...]
    feedback_keys: tuple[Identifier, ...]
    trace: tuple[RuleTrace, ...]


class ActionVector(Contract):
    vector_id: Identifier
    category: Literal["success", "idempotency", "stale_revision", "effect_conflict", "locked_scene"]
    initial_state: PlayerState
    actions: tuple[ActionRequest, ...] = Field(min_length=1)
    expected_state: PlayerState | None
    expected_error: Identifier | None
    evaluation_status: Literal["not_run"]

    @model_validator(mode="after")
    def expected_outcome(self) -> Self:
        if (self.expected_state is None) == (self.expected_error is None):
            raise ValueError("A vector requires exactly one expected outcome")
        return self


class NarrativePackage(VersionedPayload):
    evidence_package_hash: Sha256
    candidate_id: Identifier
    routes: tuple["ArtifactRef", ...] = Field(min_length=1)
    game: GameContent
    fiction_notice: Text


NarrativePackage.model_rebuild()
