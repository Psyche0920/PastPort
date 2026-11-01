"""Content-only authoring contract; runtime graph identities belong to the compiler."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import Contract, Identifier, Sha256, Text
from pastport.domain.mechanics import CoverageProblem, SourceChoiceRequirement

StoryStructure = Literal["authored_graph", "compiled_plan_v1"]


class StoryText(Contract):
    en: Text
    zh: Text


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


class StoryPlanResult(Contract):
    decision: Literal["complete", "no_feasible_story"]
    reason: Text
    plan: StoryPlan | None

    @model_validator(mode="after")
    def complete_content(self) -> Self:
        if (self.decision == "complete") != (self.plan is not None):
            raise ValueError("Complete needs a plan; infeasible must not contain one")
        return self
