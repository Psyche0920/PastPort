"""Reconcile closed native Story state without inventing initial values or outcomes."""

import json
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from pastport.domain.common import Contract, Identifier, Text
from pastport.domain.game import (
    All,
    AnyOf,
    Condition,
    EndingTable,
    Not,
    Rule,
    Scalar,
    Scene,
    SetVariable,
    Variable,
    VariableEquals,
)


class StateReference(Contract):
    name: Identifier
    path: Text
    value: Scalar
    operation: Literal["read", "write"]


class StateIssue(Contract):
    code: Literal["missing_declaration", "type_mismatch", "empty_rule", "duplicate_declaration"]
    name: Identifier
    path: Text
    reason: Text


class RemovedStateWrite(Contract):
    rule_id: Identifier
    effect_index: int
    name: Identifier
    value: Scalar
    reason: Literal["undeclared_and_never_read"] = "undeclared_and_never_read"


class RetaggedRelationshipFlag(Contract):
    rule_id: Identifier
    effect_index: int
    name: Identifier
    value: bool
    previous: Literal["set_relationship"] = "set_relationship"
    current: Literal["set_variable"] = "set_variable"
    reason: Literal["declared_boolean_flag_not_string_relationship"] = (
        "declared_boolean_flag_not_string_relationship"
    )


class StateReconciliation(Contract):
    output_text: str
    removed_writes: tuple[RemovedStateWrite, ...]
    retagged_writes: tuple[RetaggedRelationshipFlag, ...] = ()
    issues: tuple[StateIssue, ...]


class _NativeState(BaseModel):
    """Parse individual native nodes before the full game's reference validation."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    variables: tuple[Variable, ...]
    rules: tuple[Rule, ...]
    scenes: tuple[Scene, ...]
    endings: tuple[EndingTable, ...]


class NarrativeStateReconciler:
    """Remove unobservable undeclared stores; preserve all reads and declared state.

    The native wire profile exposes declared variables only. An undeclared write
    with no read anywhere has no observable Story consequence. Removing such a
    store is safer than guessing an initial value. A live missing declaration,
    type mismatch, or rule left without effects remains a validation failure.
    """

    @staticmethod
    def object(value: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(value, dict):
            raise ValueError("Expected a native Story object")
        return value

    def reads(self, condition: Condition | None, path: str) -> Iterator[StateReference]:
        if isinstance(condition, VariableEquals):
            yield StateReference(
                name=condition.name, path=path, value=condition.value, operation="read"
            )
        elif isinstance(condition, All | AnyOf):
            for index, child in enumerate(condition.conditions):
                yield from self.reads(child, f"{path}.conditions.{index}")
        elif isinstance(condition, Not):
            yield from self.reads(condition.condition, path + ".condition")

    def references(self, state: _NativeState) -> Iterator[StateReference]:
        for index, rule in enumerate(state.rules):
            yield from self.reads(rule.guard, f"rules.{index}.guard")
            for offset, effect in enumerate(rule.effects):
                if isinstance(effect, SetVariable):
                    yield StateReference(
                        name=effect.name,
                        path=f"rules.{index}.effects.{offset}",
                        value=effect.value,
                        operation="write",
                    )
        for index, scene in enumerate(state.scenes):
            for offset, task in enumerate(scene.tasks):
                yield from self.reads(task.guard, f"scenes.{index}.tasks.{offset}.guard")
            for offset, feedback in enumerate(scene.feedback):
                yield from self.reads(feedback.guard, f"scenes.{index}.feedback.{offset}.guard")
        for index, table in enumerate(state.endings):
            for offset, ending in enumerate(table.endings):
                base = f"endings.{index}.endings.{offset}"
                yield from self.reads(ending.guard, base + ".guard")
                for outcome_index, outcome in enumerate(ending.outcomes):
                    for variant_index, variant in enumerate(outcome.variants):
                        yield from self.reads(
                            variant.guard,
                            f"{base}.outcomes.{outcome_index}.variants.{variant_index}.guard",
                        )

    def reconcile(self, raw: str) -> StateReconciliation:
        document = TypeAdapter(dict[str, JsonValue]).validate_json(raw)
        draft = self.object(document.get("payload")) if "payload" in document else document
        game = self.object(self.object(draft.get("package")).get("game"))
        state = _NativeState.model_validate_json(json.dumps(game))
        declared = {variable.name: variable.initial for variable in state.variables}
        references = tuple(self.references(state))
        read_names = {ref.name for ref in references if ref.operation == "read"}
        issues: list[StateIssue] = []
        if len(declared) != len(state.variables):
            issues.append(
                StateIssue(
                    code="duplicate_declaration",
                    name="variables",
                    path="variables",
                    reason="Duplicate declarations must be resolved explicitly",
                )
            )
        raw_rules = game.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError("Expected native rules")
        removed: list[RemovedStateWrite] = []
        retagged: list[RetaggedRelationshipFlag] = []
        removed_paths: set[str] = set()
        for index, rule in enumerate(state.rules):
            dead = {
                offset
                for offset, effect in enumerate(rule.effects)
                if isinstance(effect, SetVariable)
                and effect.name not in declared
                and effect.name not in read_names
            }
            if dead and len(dead) == len(rule.effects):
                issues.append(
                    StateIssue(
                        code="empty_rule",
                        name=rule.rule_id,
                        path=f"rules.{index}.effects",
                        reason="Removing unused stores would leave no authored consequence",
                    )
                )
                continue
            target = self.object(raw_rules[index])
            raw_effects = target.get("effects")
            if not isinstance(raw_effects, list):
                raise ValueError("Expected native effects")
            for offset in sorted(dead):
                effect = rule.effects[offset]
                assert isinstance(effect, SetVariable)
                removed.append(
                    RemovedStateWrite(
                        rule_id=rule.rule_id,
                        effect_index=offset,
                        name=effect.name,
                        value=effect.value,
                    )
                )
                removed_paths.add(f"rules.{index}.effects.{offset}")
            for offset, effect in enumerate(rule.effects):
                if (
                    offset not in dead
                    and isinstance(effect, SetVariable)
                    and effect.kind == "set_relationship"
                    and type(declared.get(effect.name)) is bool
                    and type(effect.value) is bool
                ):
                    raw_effect = self.object(raw_effects[offset])
                    raw_effect["kind"] = "set_variable"
                    retagged.append(
                        RetaggedRelationshipFlag(
                            rule_id=rule.rule_id,
                            effect_index=offset,
                            name=effect.name,
                            value=bool(effect.value),
                        )
                    )
            target["effects"] = [
                effect for offset, effect in enumerate(raw_effects) if offset not in dead
            ]
        for ref in references:
            if ref.path in removed_paths:
                continue
            if ref.name not in declared:
                issues.append(
                    StateIssue(
                        code="missing_declaration",
                        name=ref.name,
                        path=ref.path,
                        reason="Referenced state needs an explicit authored type and initial value",
                    )
                )
            elif type(declared[ref.name]) is not type(ref.value):
                issues.append(
                    StateIssue(
                        code="type_mismatch",
                        name=ref.name,
                        path=ref.path,
                        reason=(
                            "Referenced scalar type differs from its declaration; "
                            "no coercion applied"
                        ),
                    )
                )
        return StateReconciliation(
            output_text=json.dumps(document, ensure_ascii=False),
            removed_writes=tuple(removed),
            retagged_writes=tuple(retagged),
            issues=tuple(issues),
        )
