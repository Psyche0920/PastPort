"""Executable wire and cross-package invariants, not historical or player validation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import JsonValue, ValidationError

from pastport.contracts import SCHEMAS
from pastport.domain.common import CanonicalSerializer, Contract, EvidenceRequest, SourceLocator
from pastport.domain.game import GameContent, PlayerState
from pastport.domain.modules import DraftRequest, ModuleResult, NarrativeDraft, ResearchRequest
from pastport.domain.packages import PackageBundle
from pastport.domain.workflow import BudgetPolicy, SkillResult

FIXTURES = Path(__file__).parent / "fixtures" / "reference"


def load[T: Contract](model: type[T], name: str) -> T:
    return model.model_validate_json((FIXTURES / name).read_bytes())


def raw(name: str) -> dict[str, JsonValue]:
    value: JsonValue = json.loads((FIXTURES / name).read_bytes())
    assert isinstance(value, dict)
    return value


def changed(data: JsonValue, path: tuple[str | int, ...], value: JsonValue) -> None:
    cursor = data
    for key in path[:-1]:
        if isinstance(key, str):
            assert isinstance(cursor, dict)
            cursor = cursor[key]
        else:
            assert isinstance(cursor, list)
            cursor = cursor[key]
    key = path[-1]
    if isinstance(key, str):
        assert isinstance(cursor, dict)
        cursor[key] = value
    else:
        assert isinstance(cursor, list)
        cursor[key] = value


@pytest.mark.parametrize("name", tuple(SCHEMAS))
def test_schema_is_valid_and_committed(name: str) -> None:
    schema = json.loads((FIXTURES.parents[2] / "schemas" / f"{name}.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("case", json.loads((FIXTURES / "manifest.json").read_bytes())["cases"])
def test_complete_wire_samples(case: dict[str, JsonValue]) -> None:
    filename, schema_name, valid = case["file"], case["schema_name"], case["valid"]
    assert isinstance(filename, str) and isinstance(schema_name, str) and isinstance(valid, bool)
    model = SCHEMAS[schema_name]
    if valid:
        result = load(model, filename)
        assert model.model_validate_json(result.model_dump_json()) == result
        Draft202012Validator(model.model_json_schema()).validate(
            json.loads(result.model_dump_json())
        )
    else:
        with pytest.raises(ValidationError):
            load(model, filename)


def test_payload_hash_is_stable_and_changes_with_content() -> None:
    bundle = load(PackageBundle, "bundle.json")
    assert CanonicalSerializer.digest(bundle.evidence) == bundle.evidence_ref.sha256
    reordered = json.dumps(json.loads(bundle.evidence.model_dump_json()), sort_keys=True)
    assert (
        CanonicalSerializer.digest(type(bundle.evidence).model_validate_json(reordered))
        == bundle.evidence_ref.sha256
    )
    changed_payload = json.loads(bundle.evidence.model_dump_json())
    changed_payload["content_version"] = "2"
    updated = type(bundle.evidence).model_validate_json(json.dumps(changed_payload))
    assert CanonicalSerializer.digest(updated) != bundle.evidence_ref.sha256


def test_nested_payloads_are_immutable() -> None:
    bundle = load(PackageBundle, "bundle.json")
    with pytest.raises(ValidationError):
        bundle.evidence.claims[0].__setattr__("text", "Changed after approval")
    assert isinstance(bundle.evidence.claims, tuple)
    assert isinstance(bundle.narrative.game.locales[0].entries, tuple)


@pytest.mark.parametrize(
    "path,value,reason",
    [
        (("reviews", "decisions", 0, "target_hash"), "0" * 64, "approval"),
        (("reviews", "decisions", 0, "environment"), "production", "approval"),
        (("reviews", "decisions", 0, "decision"), "rejected", "approval"),
        (("distribution_scope",), "public", "public"),
        (("evidence", "project_id"), "another-project", "project"),
        (("evidence_ref", "sha256"), "0" * 64, "hash"),
        (("narrative", "evidence_package_hash"), "0" * 64, "hash"),
        (("evidence", "sources", 0, "file_sha256"), "0" * 64, "locator"),
        (("route", "unknowns"), ["Entrance unknown"], "hash"),
    ],
)
def test_broken_bundle_is_rejected(
    path: tuple[str | int, ...],
    value: JsonValue,
    reason: str,
) -> None:
    data = raw("bundle.json")
    changed(data, path, value)
    with pytest.raises(ValidationError, match=reason):
        PackageBundle.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "path,value",
    [
        (("scenes", 0, "tasks", 0, "kind"), "execute-python"),
        (("scenes", 0, "tasks", 0, "spots", 0, "x"), -1),
        (("scenes", 0, "tasks", 0, "required_spot_ids"), ["not-present"]),
        (("scenes", 0, "next_scene_ids"), ["unknown-scene"]),
        (("rules", 0, "effects", 0, "item_id"), "unknown-prop"),
        (("rules", 1, "effects", 0, "value"), "true"),
        (("rules", 1, "once_key"), "once:grant-note"),
        (("rules", 0, "guard", "spot_ids"), []),
        (("decisions", 0, "options", 1, "option_id"), "help"),
        (("initial_state", "unlocked_scene_ids"), ["later-scene"]),
        (("locales", 1, "entries", 0, "key"), "missing-key"),
        (("endings", 0, "endings", 0, "fallback"), False),
    ],
)
def test_game_references_and_capabilities_are_closed(
    path: tuple[str | int, ...],
    value: JsonValue,
) -> None:
    data = load(PackageBundle, "bundle.json").narrative.game.model_dump(mode="json")
    changed(data, path, value)
    with pytest.raises(ValidationError):
        GameContent.model_validate_json(json.dumps(data))


def test_unsupported_multi_task_is_rejected() -> None:
    data = load(PackageBundle, "bundle.json").narrative.game.model_dump(mode="json")
    data["scenes"][0]["tasks"].append(deepcopy(data["scenes"][0]["tasks"][0]))
    with pytest.raises(ValidationError):
        GameContent.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("value", [True, "2", -1, float("nan"), float("inf")])
def test_budget_numbers_cannot_be_coerced_or_nonfinite(value: JsonValue) -> None:
    data = raw("budget-policy.json")
    data["max_model_requests"] = value
    with pytest.raises(ValidationError):
        BudgetPolicy.model_validate_json(json.dumps(data))


def test_source_locator_cannot_be_a_title_without_location() -> None:
    with pytest.raises(ValidationError):
        SourceLocator.model_validate_json(
            json.dumps(
                {
                    "source_id": "source-1",
                    "source_version": "1",
                    "file_sha256": "0" * 64,
                    "page_index": None,
                    "printed_page": "iii",
                    "paragraph_or_region": None,
                }
            )
        )


def test_scope_gap_does_not_require_story_candidate() -> None:
    request = load(ResearchRequest, "research-request.json")
    data = request.evidence_request.model_dump(mode="json")
    data.update(purpose="scope_gap", candidate_id=None)
    assert EvidenceRequest.model_validate_json(json.dumps(data)).candidate_id is None
    data["candidate_id"] = "fabricated-direction"
    with pytest.raises(ValidationError):
        EvidenceRequest.model_validate_json(json.dumps(data))


def test_unapproved_route_does_not_enter_draft() -> None:
    data = raw("draft-request.json")
    changed(data, ("evidence", "reviews", "decisions", 0, "decision"), "changes_requested")
    with pytest.raises(ValidationError):
        DraftRequest.model_validate_json(json.dumps(data))


def test_changed_requirements_invalidates_selection() -> None:
    data = raw("draft-request.json")
    changed(data, ("requirements", "theme_brief"), "A different story direction")
    with pytest.raises(ValidationError, match="Requirements changed"):
        DraftRequest.model_validate_json(json.dumps(data))


def test_model_cannot_emit_human_approval_or_node_alias() -> None:
    data = raw("skill-result.json")
    data["decision"] = "approved"
    with pytest.raises(ValidationError):
        SkillResult[NarrativeDraft].model_validate_json(json.dumps(data))
    data["decision"] = "complete"
    data["review_decision"] = {"approved": True}
    with pytest.raises(ValidationError):
        SkillResult[NarrativeDraft].model_validate_json(json.dumps(data))


def test_module_requests_changes_or_research_explicitly() -> None:
    for outcome in ("research_required", "changes_required"):
        with pytest.raises(ValidationError):
            ModuleResult[NarrativeDraft].model_validate_json(
                json.dumps(
                    {
                        "outcome": outcome,
                        "payload": None,
                        "issues": [],
                        "evidence_requests": [],
                        "changed_ids": [],
                        "reason": "Missing concrete detail must not be hidden.",
                    }
                )
            )


def test_json_schema_is_structural_not_a_live_approval_service() -> None:
    data = raw("invalid-stale-bundle.json")
    # JSON Schema alone cannot check hashes or query the authenticated approval database.
    Draft202012Validator(PackageBundle.model_json_schema()).validate(data)
    with pytest.raises(ValidationError):
        PackageBundle.model_validate_json(json.dumps(data))


def test_player_state_schema_has_durable_keys_and_roundtrips() -> None:
    state = load(PlayerState, "player-state.json")
    assert state.applied_rule_keys == () and state.processed_actions == ()
    assert state.package_hash == load(PackageBundle, "bundle.json").runtime_ref.sha256


def rehash_evidence_dependency(data: dict[str, JsonValue]) -> None:
    """Rebind content hashes so a targeted semantic failure is not masked by a stale hash."""
    from pastport.domain.evidence import EvidencePackage
    from pastport.domain.game import NarrativePackage
    from pastport.domain.packages import RuntimePackage

    evidence = EvidencePackage.model_validate_json(json.dumps(data["evidence"]))
    evidence_hash = CanonicalSerializer.digest(evidence)
    changed(data, ("evidence_ref", "sha256"), evidence_hash)
    changed(data, ("narrative", "evidence_package_hash"), evidence_hash)
    narrative = NarrativePackage.model_validate_json(json.dumps(data["narrative"]))
    narrative_hash = CanonicalSerializer.digest(narrative)
    changed(data, ("narrative_ref", "sha256"), narrative_hash)
    changed(data, ("runtime", "evidence_package_hash"), evidence_hash)
    changed(data, ("runtime", "narrative_package_hash"), narrative_hash)
    runtime = RuntimePackage.model_validate_json(json.dumps(data["runtime"]))
    changed(data, ("runtime_ref", "sha256"), CanonicalSerializer.digest(runtime))


@pytest.mark.parametrize(
    "path,value,error",
    [
        (("evidence", "assets", 0, "rights_state"), "unknown", "rights"),
        (("evidence", "assets", 0, "allowed_uses"), [], "rights"),
        (("evidence", "assets", 0, "mapping_state"), "provisional", "mapping"),
        (("evidence", "claims", 0, "judgment"), "insufficient", "Unsupported fact"),
        (("evidence", "claims", 0, "content_kind"), "original_fiction", "Fiction"),
        (("evidence", "claims", 0, "judgment"), "qualified", "wording"),
    ],
)
def test_rehashed_unusable_evidence_is_still_rejected(
    path: tuple[str | int, ...],
    value: JsonValue,
    error: str,
) -> None:
    data = raw("bundle.json")
    changed(data, path, value)
    rehash_evidence_dependency(data)
    with pytest.raises(ValidationError, match=error):
        PackageBundle.model_validate_json(json.dumps(data))


def test_rehashed_claim_edit_invalidates_old_approval() -> None:
    data = raw("bundle.json")
    changed(data, ("evidence", "claims", 0, "text"), "A new factual premise requires approval.")
    rehash_evidence_dependency(data)
    with pytest.raises(ValidationError, match="review target omitted"):
        PackageBundle.model_validate_json(json.dumps(data))


def test_all_schema_exports_match_models() -> None:
    # Verify byte determinism through the same public checker used by CI.
    import subprocess
    import sys

    path = FIXTURES.parents[2] / "tools" / "check_contracts.py"
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=FIXTURES.parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Contract check passed" in completed.stdout
