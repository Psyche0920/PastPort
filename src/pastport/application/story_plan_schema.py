"""Constrain content selections to the pinned evidence catalog before generation."""

from pydantic import JsonValue

from pastport.application.story_reference_contract import StoryReferenceContract
from pastport.domain.evidence import EvidencePackage


def constrain_plan_schema(schema: JsonValue, evidence: EvidencePackage) -> JsonValue:
    obj = StoryReferenceContract._object
    root = obj(schema)
    definitions = obj(root.get("$defs"))
    task = obj(obj(definitions.get("StoryPlanTask")).get("properties"))
    obj(task.get("asset_id"))["enum"] = [a.asset_id for a in evidence.assets]
    claims: list[JsonValue] = [c.claim_id for c in evidence.claims]
    obj(obj(task.get("claim_ids")).get("items"))["enum"] = claims
    source = obj(obj(definitions.get("SourceChoiceRequirement")).get("properties"))
    obj(source.get("target_claim_id"))["enum"] = claims
    obj(obj(source.get("contrast_claim_ids")).get("items"))["enum"] = claims
    return root
