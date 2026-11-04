"""Model-facing keys exclude native IDs; explicit wrong object choices remain errors."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from pastport.application.models import ServiceError
from pastport.application.story_reference_contract import StoryReferenceContract
from pastport.domain.evidence import EvidencePackage
from pastport.domain.modules import NarrativeDraft
from pastport.domain.workflow import SkillResult

FIXTURES = Path(__file__).parent / "fixtures/reference"


def test_model_schema_accepts_source_keys_and_rejects_native_uuid() -> None:
    evidence = EvidencePackage.model_validate_json((FIXTURES / "evidence.json").read_bytes())
    contract = StoryReferenceContract.from_evidence(evidence)
    schema = contract.constrain(SkillResult[NarrativeDraft].model_json_schema())
    assert isinstance(schema, (dict, bool))
    module = json.loads((FIXTURES / "draft-result.json").read_text())
    payload = SkillResult[NarrativeDraft](
        request_id="test-operation",
        skill="narrative",
        mode="draft",
        input_refs=(),
        decision="complete",
        reason_code="TEST_COMPLETE",
        reason="Synthetic schema check",
        payload=NarrativeDraft.model_validate_json(json.dumps(module["payload"])),
        issues=(),
        changed_ids=(),
        evidence_requests=(),
        tool_request=None,
    ).model_dump(mode="json")
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    payload["payload"]["authoring_report"][0]["heritage_refs"] = ["object:wrong-native-id"]
    assert list(Draft202012Validator(schema).iter_errors(payload))
    # Providers that disregard constrained generation are still rejected after metering.
    draft = NarrativeDraft.model_validate_json(json.dumps(payload["payload"]))
    with pytest.raises(ServiceError, match="not native object IDs"):
        contract.validate(draft)


def test_empty_scope_and_changed_schema_fail_before_dispatch() -> None:
    with pytest.raises(ServiceError, match="No source/asset"):
        StoryReferenceContract(()).constrain({})
    with pytest.raises(ServiceError, match="schema changed"):
        StoryReferenceContract(("claim-one",)).constrain({})
