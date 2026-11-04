"""Preview repairs preserve meaning-bearing data and leave ambiguous cases unresolved."""

import json
from typing import TypedDict

from pastport.application.preview_normalization import PreviewOutputNormalizer


class ChoiceGuard(TypedDict):
    kind: str
    decision_id: str
    option_id: str


class OptionRule(TypedDict):
    rule_id: str
    once_key: str
    event: str
    target_id: str
    guard: ChoiceGuard
    effects: list[object]


def test_fallback_priority_repair_changes_only_the_fallback_order() -> None:
    original = {
        "package": {
            "game": {
                "endings": [
                    {
                        "ending_table_id": "endings",
                        "endings": [
                            {
                                "ending_id": "conditional",
                                "fallback": False,
                                "priority": 10,
                                "guard": {
                                    "kind": "variable_equals",
                                    "name": "choice",
                                    "value": True,
                                },
                            },
                            {
                                "ending_id": "fallback",
                                "fallback": True,
                                "priority": 0,
                                "guard": None,
                            },
                        ],
                    }
                ]
            }
        },
        "unresolved_items": ["Historical association unverified"],
    }
    result = PreviewOutputNormalizer.normalize(json.dumps(original))
    expected = json.loads(json.dumps(original))
    expected["package"]["game"]["endings"][0]["endings"][1]["priority"] = 11
    assert json.loads(result.output_text) == expected
    assert len(result.repairs) == 1
    assert result.repairs[0].previous == 0
    assert result.repairs[0].current == 11


def test_ambiguous_fallbacks_are_not_guessed() -> None:
    original = {
        "package": {
            "game": {
                "endings": [
                    {
                        "ending_table_id": "endings",
                        "endings": [
                            {"ending_id": "a", "fallback": True, "priority": 0, "guard": None},
                            {"ending_id": "b", "fallback": True, "priority": 1, "guard": None},
                        ],
                    }
                ]
            }
        }
    }
    result = PreviewOutputNormalizer.normalize(json.dumps(original))
    assert not result.repairs
    assert json.loads(result.output_text) == original


def test_exclusive_option_rules_receive_unique_once_keys_without_changing_meaning() -> None:
    rules: list[OptionRule] = [
        {
            "rule_id": "r-" + option,
            "once_key": "shared",
            "event": "option_chosen",
            "target_id": "d",
            "guard": {"kind": "choice_equals", "decision_id": "d", "option_id": option},
            "effects": [],
        }
        for option in ("a", "b")
    ]
    original = {"package": {"game": {"rules": rules, "endings": []}}}
    result = PreviewOutputNormalizer.normalize(json.dumps(original))
    repaired = json.loads(result.output_text)
    for before, after in zip(rules, repaired["package"]["game"]["rules"], strict=True):
        assert after == before | {"once_key": "once:" + before["rule_id"]}
    assert len(result.once_key_repairs) == 2
    rules[1]["guard"]["option_id"] = "a"
    ambiguous = PreviewOutputNormalizer.normalize(json.dumps(original))
    assert not ambiguous.once_key_repairs
    assert json.loads(ambiguous.output_text) == original
