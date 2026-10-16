"""Immutable wire contracts and content identity; no framework or provider imports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "0.1.0"
Identifier = Annotated[
    str, Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
]
Text = Annotated[str, Field(min_length=1, max_length=10000, pattern=r"\S")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegative = Annotated[int, Field(ge=0, le=9007199254740991)]
Positive = Annotated[int, Field(gt=0, le=9007199254740991)]
Version = Literal["0.1.0"]
Locale = Literal["en", "zh"]
Environment = Literal["test", "production"]
Owner = Literal["evidence", "narrative", "assembly", "runtime", "workflow"]
ArtifactKind = Literal[
    "source",
    "source_manifest",
    "source_index",
    "candidate_set",
    "route",
    "evidence",
    "narrative",
    "runtime",
    "policy",
    "skill",
    "model_config",
    "requirements",
    "report",
]


class Contract(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
        validate_default=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )


class ArtifactRef(Contract):
    artifact_id: Identifier
    project_id: Identifier
    kind: ArtifactKind
    schema_version: Version
    content_version: Identifier
    sha256: Sha256


class VersionedPayload(Contract):
    project_id: Identifier
    schema_version: Version
    content_version: Identifier


class SourceLocator(Contract):
    source_id: Identifier
    source_version: Identifier
    file_sha256: Sha256
    page_index: NonNegative | None
    printed_page: Text | None
    paragraph_or_region: Text | None

    @model_validator(mode="after")
    def located(self) -> Self:
        if self.page_index is None and self.paragraph_or_region is None:
            raise ValueError("An original page or region locator is required")
        return self


class ValidationIssue(Contract):
    code: Identifier
    severity: Literal["blocking", "warning"]
    owner: Owner
    artifact_id: Identifier | None
    json_pointer: Annotated[str, Field(pattern=r"^(?:/.*)?$")]
    message: Text
    remediation: Text


class ReviewDecision(Contract):
    decision_id: Identifier
    gate: Literal["evidence", "narrative", "publication"]
    target_id: Identifier
    target_version: Identifier
    target_hash: Sha256
    decision: Literal["approved", "changes_requested", "rejected"]
    reason: Text
    actor_id: Identifier
    created_at: AwareDatetime
    environment: Environment

    @field_validator("created_at")
    @classmethod
    def utc_only(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("Timestamp must be UTC")
        return value


class FolderInput(Contract):
    provider: Literal["google_drive", "local_manifest"]
    folder_id: Identifier
    manifest_ref: ArtifactRef | None


class ProjectRequirements(VersionedPayload):
    scope_site_ids: tuple[Identifier, ...] | None
    languages: tuple[Locale, ...]
    target_story_minutes: Positive | None
    theme_brief: Text
    accessibility_requirements: tuple[Text, ...]
    distribution_scope: Literal["internal_preview", "public"]

    @field_validator("languages")
    @classmethod
    def bilingual(cls, value: tuple[Locale, ...]) -> tuple[Locale, ...]:
        if set(value) != {"en", "zh"} or len(value) != 2:
            raise ValueError("The initial profile requires en and zh exactly once")
        return value


class EvidenceRequest(Contract):
    request_id: Identifier
    project_id: Identifier
    purpose: Literal["scope_gap", "direction"]
    candidate_id: Identifier | None
    question: Text
    reason: Text
    affected_ids: tuple[Identifier, ...]
    existing_source_ids: tuple[Identifier, ...]
    required_evidence: tuple[Text, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def check_candidate(self) -> Self:
        if (self.purpose == "scope_gap") != (self.candidate_id is None):
            raise ValueError("scope_gap requires null candidate; direction requires a candidate")
        return self


class CanonicalSerializer:
    """Hash validated payloads only; approvals and paths are separate objects."""

    @staticmethod
    def encode(payload: Contract) -> bytes:
        return json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def digest(cls, payload: Contract) -> str:
        return hashlib.sha256(cls.encode(payload)).hexdigest()

    @classmethod
    def reference(
        cls, payload: VersionedPayload, artifact_id: str, kind: ArtifactKind
    ) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=artifact_id,
            project_id=payload.project_id,
            kind=kind,
            schema_version=payload.schema_version,
            content_version=payload.content_version,
            sha256=cls.digest(payload),
        )


def unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(f"Duplicate {label}")
