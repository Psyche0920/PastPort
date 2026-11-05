"""Content-only authoring contract; runtime graph identities belong to the compiler."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import Contract, Identifier, Sha256, Text
from pastport.domain.investigation_plan import InvestigationDesign
from pastport.domain.mechanics import CoverageProblem, SourceChoiceRequirement

StoryStructure = Literal["authored_graph", "compiled_plan_v1", "compiled_branch_v1"]


class StoryText(Contract):
    en: Text
    zh: Text


class OpeningPerson(Contract):
    """Public opening introduction; runtime character identities are not model-authored."""

    name: StoryText
    introduction: StoryText


class OpeningStation(Contract):
    asset_id: Annotated[str, Field(pattern=r"^object-[1-9][0-9]*$")]
    title: StoryText
    purpose: StoryText


class StoryOpening(Contract):
    """Only information available before investigation, not the hidden solution."""

    title: StoryText
    setting: StoryText
    situation: StoryText
    player_role: StoryText
    central_question: StoryText
    people: tuple[OpeningPerson, ...] = Field(max_length=10)
    stations: tuple[OpeningStation, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        if len({station.asset_id for station in self.stations}) != len(self.stations):
            raise ValueError("Opening station identities must be unique")
        for locale in ("en", "zh"):
            names = [getattr(person.name, locale).casefold() for person in self.people]
            if len(set(names)) != len(names):
                raise ValueError("Opening people need distinct localized names")
        return self


def validate_opening_assets(opening: StoryOpening | None, assets: set[str]) -> None:
    if opening is not None and {station.asset_id for station in opening.stations} != assets:
        raise ValueError("Opening stations must cover exactly the story-selected assets")


class ReadingPlan(Contract):
    kind: Literal["source_reading"]


class CoveragePlan(Contract):
    kind: Literal["coverage"]
    capability_id: Identifier
    rules: CoverageProblem
    source_requirement: SourceChoiceRequirement
    learning_goal: Text
    fiction_notice: Text


class TaskReasoning(Contract):
    property_used: Text
    player_premises: tuple[Text, ...] = Field(min_length=1, max_length=8)
    inference_steps: tuple[Text, ...] = Field(min_length=1, max_length=8)
    accepted_answer: Text
    removal_test: Text
    substitution_test: Text
    counterexample: Text


class StoryPlanTask(Contract):
    # These are upstream selections, never invented runtime identifiers.
    asset_id: Annotated[str, Field(pattern=r"^object-[1-9][0-9]*$")]
    claim_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=8)
    view_id: Identifier
    title: StoryText
    dialogue: StoryText
    objective: StoryText
    feedback: StoryText
    hints: tuple[StoryText, ...] = Field(min_length=1, max_length=3)
    accessibility: StoryText
    gameplay: Annotated[ReadingPlan | CoveragePlan, Field(discriminator="kind")]
    reasoning: TaskReasoning


class StoryPlanChoice(Contract):
    label: StoryText
    consequence: StoryText


class StoryPlan(Contract):
    structure: Literal["compiled_plan_v1"]
    protagonist_name: StoryText
    protagonist_goal: StoryText
    tasks: tuple[StoryPlanTask, ...] = Field(min_length=1, max_length=8)
    choices: tuple[StoryPlanChoice, ...] = Field(min_length=2, max_length=4)
    fiction_notice: Text
    capability_catalog_sha256: Sha256
    unresolved_items: tuple[Text, ...]
    opening_context: StoryOpening | None = None
    activity_design: InvestigationDesign | None = None

    @model_validator(mode="after")
    def opening_coverage(self) -> Self:
        validate_opening_assets(self.opening_context, {task.asset_id for task in self.tasks})
        validate_activity_design(self.activity_design, self.tasks, {len(self.tasks)})
        return self


class StoryPlanResult(Contract):
    decision: Literal["complete", "no_feasible_story"]
    reason: Text
    plan: StoryPlan | None

    @model_validator(mode="after")
    def complete_content(self) -> Self:
        if (self.decision == "complete") != (self.plan is not None):
            raise ValueError("Complete needs a plan; infeasible must not contain one")
        return self


class StoryInvestigation(Contract):
    """One exclusive route; findings are fictional notebook content, not source approval."""

    label: StoryText
    tasks: tuple[StoryPlanTask, ...] = Field(min_length=1, max_length=3)
    finding: StoryText
    reunion_feedback: StoryText
    ending_consequences: tuple[StoryText, ...] = Field(min_length=2, max_length=4)


class BranchStoryPlan(Contract):
    """Bounded foldback; models select content, never runtime variables or rules."""

    structure: Literal["compiled_branch_v1"]
    protagonist_name: StoryText
    protagonist_goal: StoryText
    opening: tuple[StoryPlanTask, ...] = Field(min_length=1, max_length=3)
    investigations: tuple[StoryInvestigation, ...] = Field(min_length=2, max_length=4)
    reunion: tuple[StoryPlanTask, ...] = Field(min_length=1, max_length=3)
    choices: tuple[StoryPlanChoice, ...] = Field(min_length=2, max_length=4)
    fiction_notice: Text
    capability_catalog_sha256: Sha256
    unresolved_items: tuple[Text, ...]
    opening_context: StoryOpening | None = None
    activity_design: InvestigationDesign | None = None

    @model_validator(mode="after")
    def consequence_coverage(self) -> Self:
        tasks = (
            *self.opening,
            *(task for route in self.investigations for task in route.tasks),
            *self.reunion,
        )
        validate_opening_assets(self.opening_context, {task.asset_id for task in tasks})
        validate_activity_design(self.activity_design, tasks, {len(self.opening), len(tasks)})
        if any(
            len(route.ending_consequences) != len(self.choices) for route in self.investigations
        ):
            raise ValueError("Every investigation needs a consequence for each final choice")
        return self


class BranchStoryPlanResult(Contract):
    decision: Literal["complete", "no_feasible_story"]
    reason: Text
    plan: BranchStoryPlan | None

    @model_validator(mode="after")
    def complete_content(self) -> Self:
        if (self.decision == "complete") != (self.plan is not None):
            raise ValueError("Complete needs a plan; infeasible must not contain one")
        return self


def validate_activity_design(
    design: InvestigationDesign | None,
    tasks: tuple[StoryPlanTask, ...],
    decisions: set[int],
) -> None:
    if design is None:
        return
    claims = {claim for task in tasks for claim in task.claim_ids}
    for image in design.asset_manifest:
        if not set(image.source_claim_ids) <= claims:
            raise ValueError("Investigation image uses an unselected source claim")
    for row in design.interludes:
        if row.after_task > len(tasks) or row.after_task in decisions:
            raise ValueError("Investigation needs a task with one non-decision successor")
        view = tasks[row.after_task - 1].view_id
        available = {
            int(task.asset_id.removeprefix("object-")) for task in tasks if task.view_id == view
        }
        if row.source_object not in available or not set(row.required_sources) <= available:
            raise ValueError("Investigation sources need registered selections in the anchor view")
