"""Small narrative-state patches that leave authored prose and evidence untouched."""

from pydantic import Field

from pastport.domain.common import Identifier, VersionedPayload
from pastport.domain.game import EndingTable, Rule, Variable


class TaskReferenceRepair(VersionedPayload):
    task_id: Identifier
    character_id: Identifier
    evidence_refs: tuple[Identifier, ...] = Field(min_length=1)
    prerequisite_task_ids: tuple[Identifier, ...]
    effect_rule_ids: tuple[Identifier, ...] = Field(min_length=1)
    consequence_read_scene_id: Identifier


class NarrativeRepairPatch(VersionedPayload):
    task_references: tuple[TaskReferenceRepair, ...] = Field(min_length=1)
    variables: tuple[Variable, ...]
    rules: tuple[Rule, ...]
    endings: tuple[EndingTable, ...] = Field(min_length=1)
