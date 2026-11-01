"""Compile model-selectable evidence keys; native object IDs stay program-owned."""

from dataclasses import dataclass

from pydantic import JsonValue

from pastport.application.models import ServiceError
from pastport.domain.evidence import EvidencePackage
from pastport.domain.modules import NarrativeDraft


@dataclass(frozen=True, slots=True)
class StoryReferenceContract:
    keys: tuple[str, ...]

    @classmethod
    def from_evidence(cls, evidence: EvidencePackage) -> "StoryReferenceContract":
        return cls(tuple(sorted({*(claim.claim_id for claim in evidence.claims),
                                 *(asset.asset_id for asset in evidence.assets)})))

    @staticmethod
    def _object(value: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(value, dict):
            raise ServiceError("OUTPUT_SCHEMA_NOT_ALLOWED", "Story reference schema changed")
        return value

    def constrain(self, schema: JsonValue) -> JsonValue:
        if not self.keys:
            raise ServiceError("STORY_REFERENCE_SCOPE_EMPTY", "No source/asset keys are registered")
        root = self._object(schema)
        definitions = self._object(root.get("$defs"))
        report = self._object(definitions.get("AuthoringTaskReport"))
        properties = self._object(report.get("properties"))
        references = self._object(properties.get("heritage_refs"))
        items = self._object(references.get("items"))
        items["enum"] = list(self.keys)
        return root

    def validate(self, draft: NarrativeDraft) -> None:
        allowed = set(self.keys)
        if any(not set(report.heritage_refs) <= allowed for report in draft.authoring_report):
            raise ServiceError(
                "MODEL_OUTPUT_INVALID",
                "Author report must select registered source/asset keys, not native object IDs",
            )
