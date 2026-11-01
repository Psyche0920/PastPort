"""Mechanical repairs for explicitly authorized internal-preview model output."""

import json

from pydantic import JsonValue, TypeAdapter

from pastport.application.narrative_state import (
    NarrativeStateReconciler,
    RemovedStateWrite,
    RetaggedRelationshipFlag,
    StateIssue,
)
from pastport.domain.common import Contract, Identifier, NonNegative


class EndingPriorityRepair(Contract):
    table_id: Identifier
    ending_id: Identifier
    previous: NonNegative
    current: NonNegative


class OnceKeyRepair(Contract):
    rule_id: Identifier
    previous: Identifier
    current: Identifier


class PreviewNormalization(Contract):
    output_text: str
    repairs: tuple[EndingPriorityRepair, ...]
    once_key_repairs: tuple[OnceKeyRepair, ...] = ()
    state_repairs: tuple[RemovedStateWrite, ...] = ()
    state_issues: tuple[StateIssue, ...] = ()
    relationship_flag_repairs: tuple[RetaggedRelationshipFlag, ...] = ()


class PreviewOutputNormalizer:
    """Place an unconditional fallback last without changing story or branch predicates."""

    @staticmethod
    def object(value: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    @classmethod
    def normalize(cls, raw: str) -> PreviewNormalization:
        document = TypeAdapter(dict[str, JsonValue]).validate_json(raw)
        draft = cls.object(document.get("payload")) if "payload" in document else document
        package = cls.object(draft.get("package"))
        game = cls.object(package.get("game"))
        tables = game.get("endings")
        if not isinstance(tables, list):
            raise ValueError("Expected ending tables")
        repairs: list[EndingPriorityRepair] = []
        for item in tables:
            table = cls.object(item)
            endings = table.get("endings")
            if not isinstance(endings, list):
                raise ValueError("Expected endings")
            entries = [cls.object(ending) for ending in endings]
            fallbacks = [ending for ending in entries if ending.get("fallback") is True]
            ordinary = [ending for ending in entries if ending.get("fallback") is False]
            if len(fallbacks) != 1 or not ordinary:
                continue
            fallback = fallbacks[0]
            priorities = [ending.get("priority") for ending in ordinary]
            previous = fallback.get("priority")
            if (
                not isinstance(previous, int)
                or isinstance(previous, bool)
                or any(not isinstance(p, int) or isinstance(p, bool) for p in priorities)
                or fallback.get("guard") is not None
            ):
                continue
            numeric = [p for p in priorities if isinstance(p, int)]
            current = max(numeric) + 1
            if previous >= current:
                continue
            repair = EndingPriorityRepair.model_validate(
                dict(
                    table_id=table.get("ending_table_id"),
                    ending_id=fallback.get("ending_id"),
                    previous=previous,
                    current=current,
                )
            )
            fallback["priority"] = current
            repairs.append(repair)
        once_repairs: list[OnceKeyRepair] = []
        raw_rules = game.get("rules", [])
        if isinstance(raw_rules, list):
            rules = [cls.object(item) for item in raw_rules]
            groups: dict[str, list[dict[str, JsonValue]]] = {}
            used = {r["once_key"] for r in rules if isinstance(r.get("once_key"), str)}
            for rule in rules:
                key = rule.get("once_key")
                if isinstance(key, str):
                    groups.setdefault(key, []).append(rule)
            for key, group in groups.items():
                if len(group) < 2:
                    continue
                choices = [cls.choice(rule.get("guard")) for rule in group]
                targets = {str(rule.get("target_id")) for rule in group}
                identifiers = [rule.get("rule_id") for rule in group]
                if (
                    len(targets) != 1
                    or any(rule.get("event") != "option_chosen" for rule in group)
                    or any(choice is None or choice[0] not in targets for choice in choices)
                    or len(set(choices)) != len(choices)
                    or len(set(str(i) for i in identifiers)) != len(identifiers)
                ):
                    continue
                for rule in group:
                    identifier = rule.get("rule_id")
                    if not isinstance(identifier, str):
                        raise ValueError("Invalid rule identity")
                    current_key = "once:" + identifier
                    if current_key in used:
                        raise ValueError("Canonical once-key collision")
                    used.add(current_key)
                    rule["once_key"] = current_key
                    once_repairs.append(
                        OnceKeyRepair(rule_id=identifier, previous=key, current=current_key)
                    )
        output_text = json.dumps(document, ensure_ascii=False)
        state_repairs: tuple[RemovedStateWrite, ...] = ()
        relationship_flag_repairs: tuple[RetaggedRelationshipFlag, ...] = ()
        state_issues: tuple[StateIssue, ...] = ()
        # Minimal preview-normalizer callers may provide only ending tables.
        # State reconciliation requires the complete native state surface.
        if all(key in game for key in ("variables", "rules", "scenes", "endings")):
            reconciled = NarrativeStateReconciler().reconcile(output_text)
            output_text = reconciled.output_text
            state_repairs, state_issues = reconciled.removed_writes, reconciled.issues
            relationship_flag_repairs = reconciled.retagged_writes
        return PreviewNormalization(
            output_text=output_text,
            repairs=tuple(repairs),
            once_key_repairs=tuple(once_repairs),
            state_repairs=state_repairs,
            state_issues=state_issues,
            relationship_flag_repairs=relationship_flag_repairs,
        )

    @classmethod
    def choice(cls, value: JsonValue) -> tuple[str, str] | None:
        """Find one mandatory exact choice; OR guards are deliberately excluded."""
        if not isinstance(value, dict):
            return None
        if value.get("kind") == "choice_equals":
            decision, option = value.get("decision_id"), value.get("option_id")
            return (
                (decision, option)
                if isinstance(decision, str) and isinstance(option, str)
                else None
            )
        if value.get("kind") == "all":
            conditions = value.get("conditions")
            if isinstance(conditions, list):
                choices = [choice for condition in conditions if (choice := cls.choice(condition))]
                return choices[0] if len(choices) == 1 else None
        return None
