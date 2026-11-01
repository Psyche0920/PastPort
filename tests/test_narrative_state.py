"""State reconciliation changes dead stores only; live state is never guessed."""

import json
from pathlib import Path

import pytest

from pastport.application.narrative_state import NarrativeStateReconciler
from pastport.domain.modules import NarrativeDraft

FIXTURE = Path(__file__).parent / "fixtures/reference/draft-result.json"


def original() -> dict:
    return json.loads(FIXTURE.read_text())


def test_dead_store_removal_preserves_all_prose_sources_guards_and_other_effects() -> None:
    expected = original()
    document = original()
    rule = document["payload"]["package"]["game"]["rules"][0]
    rule["effects"].append({"kind": "set_variable", "name": "unused", "value": "metadata"})
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    assert json.loads(result.output_text) == expected
    assert not result.issues
    assert len(result.removed_writes) == 1
    assert result.removed_writes[0].name == "unused"
    NarrativeDraft.model_validate_json(json.dumps(json.loads(result.output_text)["payload"]))


@pytest.mark.parametrize("location", ["rule", "task", "feedback", "ending", "variant"])
def test_live_missing_state_in_every_guard_surface_is_preserved_as_an_error(location: str) -> None:
    document = original()
    game = document["payload"]["package"]["game"]
    condition = {"kind": "variable_equals", "name": "missing", "value": True}
    nested = {"kind": "not", "condition": {"kind": "all", "conditions": [condition]}}
    if location == "rule":
        game["rules"][0]["guard"] = nested
    elif location == "task":
        game["scenes"][0]["tasks"][0]["guard"] = nested
    elif location == "feedback":
        game["scenes"][0]["feedback"].append(
            {"feedback_id": "feedback-missing", "guard": nested, "text_key": "missing.feedback"}
        )
    elif location == "ending":
        table = game["endings"][0]
        for ending in table["endings"]:
            if ending["fallback"]:
                ending["priority"] = 100
        table["endings"].insert(
            0,
            {
                "ending_id": "missing-state",
                "priority": 0,
                "guard": nested,
                "fallback": False,
                "outcomes": [
                    {
                        "outcome_id": "missing",
                        "label_key": "label",
                        "text_key": "body",
                        "variants": [],
                    }
                ],
            },
        )
    else:
        game["endings"][0]["endings"][0]["outcomes"][0]["variants"].append(
            {"variant_id": "missing-state", "priority": 0, "guard": nested, "text_key": "body"}
        )
    game["rules"][0]["effects"].append(
        {"kind": "set_relationship", "name": "missing", "value": True}
    )
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    assert json.loads(result.output_text) == document
    assert not result.removed_writes
    assert any(
        issue.name == "missing" and issue.code == "missing_declaration" for issue in result.issues
    )
    with pytest.raises(ValueError):
        NarrativeDraft.model_validate_json(json.dumps(json.loads(result.output_text)["payload"]))


def test_declared_scalar_type_is_not_coerced_or_removed() -> None:
    document = original()
    game = document["payload"]["package"]["game"]
    game["variables"].append({"name": "boolean-state", "initial": False})
    game["rules"][0]["effects"].append(
        {"kind": "set_variable", "name": "boolean-state", "value": 0}
    )
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    assert json.loads(result.output_text) == document
    assert not result.removed_writes
    assert any(issue.code == "type_mismatch" for issue in result.issues)


def test_rule_is_not_erased_when_it_would_have_no_consequence() -> None:
    document = original()
    document["payload"]["package"]["game"]["rules"][0]["effects"] = [
        {"kind": "set_variable", "name": "missing", "value": True}
    ]
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    assert json.loads(result.output_text) == document
    assert not result.removed_writes
    assert any(issue.code == "empty_rule" for issue in result.issues)


def test_declared_boolean_relationship_flag_retags_only_the_operation() -> None:
    document = original()
    game = document["payload"]["package"]["game"]
    game["variables"].append({"name": "support_flag", "initial": False})
    game["rules"][0]["effects"].append(
        {"kind": "set_relationship", "name": "support_flag", "value": True}
    )
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    expected = json.loads(json.dumps(document))
    expected["payload"]["package"]["game"]["rules"][0]["effects"][-1]["kind"] = "set_variable"
    assert json.loads(result.output_text) == expected
    assert len(result.retagged_writes) == 1 and not result.issues
    assert result.retagged_writes[0].value is True
    NarrativeDraft.model_validate_json(json.dumps(expected["payload"]))


def test_string_relationship_is_unchanged_and_type_conflicts_are_not_coerced() -> None:
    document = original()
    game = document["payload"]["package"]["game"]
    game["variables"].append({"name": "relation", "initial": "neutral"})
    game["rules"][0]["effects"].append(
        {"kind": "set_relationship", "name": "relation", "value": "supportive"}
    )
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    assert not result.retagged_writes and json.loads(result.output_text) == document
    game["rules"][0]["effects"][-1]["value"] = True
    result = NarrativeStateReconciler().reconcile(json.dumps(document))
    assert not result.retagged_writes
    assert any(issue.code == "type_mismatch" for issue in result.issues)
