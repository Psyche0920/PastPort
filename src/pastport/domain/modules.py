"""Typed module messages for independent implementation against contract 0.1.0."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import (
    ArtifactRef,
    CanonicalSerializer,
    Contract,
    EvidenceRequest,
    FolderInput,
    Identifier,
    NonNegative,
    ProjectRequirements,
    Sha256,
    SourceLocator,
    Text,
    ValidationIssue,
    VersionedPayload,
    unique,
)
from pastport.domain.evidence import (
    Asset,
    Claim,
    EvidencePackage,
    RouteRecord,
    Source,
    SourceIndexDraft,
    SourceManifestDraft,
)
from pastport.domain.game import NarrativePackage, RuntimeCapabilities
from pastport.domain.mechanics import CoverageProblem, SourceChoiceRequirement
from pastport.domain.packages import ReviewSnapshot, RuntimePackage, ValidationReport


class ModuleResult[T: Contract](Contract):
    outcome: Literal[
        "completed", "research_required", "changes_required", "blocked", "no_feasible_story"
    ]
    payload: T | None
    issues: tuple[ValidationIssue, ...]
    evidence_requests: tuple[EvidenceRequest, ...]
    changed_ids: tuple[Identifier, ...]
    reason: Text

    @model_validator(mode="after")
    def complete_or_explain(self) -> Self:
        if self.outcome == "completed" and self.payload is None:
            raise ValueError("Completed module operations require their typed payload")
        if self.outcome == "research_required" and not self.evidence_requests:
            raise ValueError("Research outcome requires a concrete request")
        if self.outcome == "changes_required" and not self.changed_ids:
            raise ValueError("Changes outcome requires affected IDs")
        return self


class CandidateScore(Contract):
    dimension: Literal["evidence", "visual", "character", "solvability", "spatial"]
    score: int = Field(ge=0, le=4)
    reason: Text


class StoryCandidate(Contract):
    candidate_id: Identifier
    premise: Text
    source_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    supported_opportunities: tuple[Text, ...] = Field(min_length=1)
    blocking_gaps: tuple[Text, ...]
    proposed_player_actions: tuple[Text, ...] = Field(min_length=1)
    human_work_estimate_minutes: NonNegative | None
    dimension_scores: tuple[CandidateScore, ...] = Field(min_length=5, max_length=5)
    recommendation_reason: Text
    reversal_conditions: tuple[Text, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        unique((x.dimension for x in self.dimension_scores), "candidate score dimensions")
        return self


class CandidateSetDraft(VersionedPayload):
    candidates: tuple[StoryCandidate, ...]
    unresolved_items: tuple[Text, ...]

    @model_validator(mode="after")
    def unique_candidates(self) -> Self:
        unique((x.candidate_id for x in self.candidates), "candidate IDs")
        return self


class SelectedCandidate(Contract):
    project_id: Identifier
    candidate_set_ref: ArtifactRef
    candidate_id: Identifier
    requirements_ref: ArtifactRef
    policy_ref: ArtifactRef
    actor_id: Identifier
    reason: Text

    @model_validator(mode="after")
    def bound_selection(self) -> Self:
        for ref, kind in (
            (self.candidate_set_ref, "candidate_set"),
            (self.requirements_ref, "requirements"),
            (self.policy_ref, "policy"),
        ):
            if ref.project_id != self.project_id or ref.kind != kind:
                raise ValueError("Selected candidate reference mismatch")
        return self


class EvidenceFindings(VersionedPayload):
    request_id: Identifier
    sources: tuple[Source, ...]
    claims: tuple[Claim, ...]
    assets: tuple[Asset, ...]
    route_candidates: tuple[RouteRecord, ...]
    unresolved_items: tuple[Text, ...]
    index: SourceIndexDraft


class AuthoringTaskReport(Contract):
    task_id: Identifier
    player_action_id: Identifier
    heritage_refs: tuple[Identifier, ...] = Field(min_length=1)
    property_used: Text
    premise_source_ids: tuple[Identifier, ...] = Field(min_length=1)
    player_premises: tuple[Text, ...] = Field(min_length=1)
    inference_steps: tuple[Text, ...] = Field(min_length=1)
    accepted_answer: Text
    character_goal: Identifier
    effect_ids: tuple[Identifier, ...] = Field(min_length=1)
    consequence_read_scene_id: Identifier
    observable_feedback: Text
    removal_test: Text
    substitution_test: Text
    counterexample: Text


class TaskSpatialIntent(Contract):
    """Story chooses registered identities; environment owns coordinates and physics."""

    task_id: Identifier
    object_number: int = Field(ge=1)
    view_id: Identifier
    station_id: Identifier
    interaction: Literal["inspect_linked_source"]


class TaskReadingIntent(Contract):
    kind: Literal["source_reading"] = "source_reading"
    task_id: Identifier
    capability_id: Literal["source-reading:1"] = "source-reading:1"


class TaskTilingIntent(Contract):
    """Explicit reconstruction exercise, not evidence of an actual historic layout."""

    kind: Literal["coverage"] = "coverage"
    task_id: Identifier
    capability_id: Identifier
    rules: CoverageProblem
    source_requirement: SourceChoiceRequirement
    learning_goal: Text
    fiction_notice: Text


TaskGameplayIntent = Annotated[TaskReadingIntent | TaskTilingIntent, Field(discriminator="kind")]


class NarrativeDraft(Contract):
    package: NarrativePackage
    # Older drafts remain readable; new Story automation requires exact coverage.
    spatial_intents: tuple[TaskSpatialIntent, ...] = ()
    gameplay_intents: tuple[TaskGameplayIntent, ...] = ()
    capability_catalog_sha256: Sha256 | None = None
    authoring_report: tuple[AuthoringTaskReport, ...] = Field(min_length=1)
    unresolved_items: tuple[Text, ...]

    @property
    def tiling_intents(self) -> tuple[TaskTilingIntent, ...]:
        return tuple(
            intent for intent in self.gameplay_intents if isinstance(intent, TaskTilingIntent)
        )


class NarrativeReview(Contract):
    narrative_ref: ArtifactRef
    issues: tuple[ValidationIssue, ...]
    counterexamples: tuple[Text, ...]
    human_review_required: Literal[True]


class LockedField(Contract):
    json_pointer: Text
    value_sha256: Sha256


class ChangeImpactReport(Contract):
    before_ref: ArtifactRef
    after_ref: ArtifactRef
    changed_ids: tuple[Identifier, ...]
    change_kinds: tuple[
        Literal[
            "fact",
            "rule",
            "character_causality",
            "translation",
            "media_presentation",
            "rights",
        ],
        ...,
    ]
    affected_scene_ids: tuple[Identifier, ...]
    invalidated_decision_ids: tuple[Identifier, ...]
    reusable_decision_ids: tuple[Identifier, ...]
    reason: Text
    analysis_status: Literal["complete", "uncertain"]


class RevisionRequest(Contract):
    request_id: Identifier
    feedback: Text
    target_ids: tuple[Identifier, ...] = Field(min_length=1)
    reason: Text
    locked_fields: tuple[LockedField, ...]


class ApprovedEvidenceView(Contract):
    """Snapshot binding only; the caller must consult the authoritative review service."""

    evidence: EvidencePackage
    evidence_ref: ArtifactRef
    route: RouteRecord
    approved_route_ref: ArtifactRef
    reviews: ReviewSnapshot

    @model_validator(mode="after")
    def snapshot_binding(self) -> Self:
        for payload, ref, kind in (
            (self.evidence, self.evidence_ref, "evidence"),
            (self.route, self.approved_route_ref, "route"),
        ):
            if (
                ref.project_id != self.evidence.project_id
                or payload.project_id != self.evidence.project_id
                or ref.kind != kind
                or ref.sha256 != CanonicalSerializer.digest(payload)
                or ref.content_version != payload.content_version
            ):
                raise ValueError("Approved evidence view hash/project mismatch")
            if not any(
                target.target_id == ref.artifact_id
                and target.sha256 == ref.sha256
                and target.version == ref.content_version
                and target.gate == "evidence"
                for target in self.reviews.required_targets
            ):
                raise ValueError("Evidence/route review target missing")
        if self.approved_route_ref not in self.evidence.route_refs or self.route.unknowns:
            raise ValueError("Route not bound or required route unresolved")
        return self


class InventoryRequest(Contract):
    folder: FolderInput
    requirements: ProjectRequirements
    policy_ref: ArtifactRef

    @model_validator(mode="after")
    def policy_binding(self) -> Self:
        if (
            self.policy_ref.kind != "policy"
            or self.policy_ref.project_id != self.requirements.project_id
        ):
            raise ValueError("Policy must belong to the requested project")
        return self


class IndexRequest(Contract):
    manifest: SourceManifestDraft
    source_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    requirements: ProjectRequirements

    @model_validator(mode="after")
    def index_inputs(self) -> Self:
        project = self.requirements.project_id
        if self.manifest.project_id != project or any(
            ref.project_id != project or ref.kind != "source" for ref in self.source_refs
        ):
            raise ValueError("Cross-project index inputs")
        return self


class ResearchRequest(Contract):
    index: SourceIndexDraft
    evidence_request: EvidenceRequest
    selected_candidate: SelectedCandidate | None
    existing_findings: tuple[EvidenceFindings, ...]

    @model_validator(mode="after")
    def direction_binding(self) -> Self:
        request = self.evidence_request
        if self.index.project_id != request.project_id:
            raise ValueError("Cross-project research input")
        selected = self.selected_candidate
        if request.purpose == "direction":
            if (
                selected is None
                or selected.candidate_id != request.candidate_id
                or selected.project_id != request.project_id
            ):
                raise ValueError("Direction research needs the selected candidate")
        elif selected is not None:
            raise ValueError("Scope research has no selected candidate")
        return self


class DiscoverRequest(Contract):
    index: SourceIndexDraft
    requirements: ProjectRequirements
    runtime_capabilities: RuntimeCapabilities

    @model_validator(mode="after")
    def project_binding(self) -> Self:
        if self.index.project_id != self.requirements.project_id:
            raise ValueError("Cross-project discovery")
        return self


class DraftRequest(Contract):
    structure_profile: Literal["authored_graph", "compiled_plan_v1"] = "authored_graph"
    authoring_mode: Literal["reviewed", "internal_preview"] = "reviewed"
    host_constraints: tuple[Text, ...] = ()
    evidence: ApprovedEvidenceView
    selected_candidate: SelectedCandidate
    requirements: ProjectRequirements
    runtime_capabilities: RuntimeCapabilities
    locked_fields: tuple[LockedField, ...]

    @model_validator(mode="after")
    def selected_inputs(self) -> Self:
        selected = self.selected_candidate
        project = self.evidence.evidence.project_id
        if selected.project_id != project or self.requirements.project_id != project:
            raise ValueError("Cross-project draft input")
        if self.evidence.route.candidate_id != selected.candidate_id:
            raise ValueError("Route belongs to a different story direction")
        if selected.requirements_ref.sha256 != CanonicalSerializer.digest(self.requirements):
            raise ValueError("Requirements changed since direction confirmation")
        return self


class ReviseRequest(Contract):
    draft_request: DraftRequest
    narrative: NarrativeDraft
    revision_request: RevisionRequest
    impact: ChangeImpactReport | None

    @model_validator(mode="after")
    def same_draft(self) -> Self:
        if self.narrative.package.project_id != self.draft_request.requirements.project_id:
            raise ValueError("Revision draft belongs to another project")
        return self


class NarrativeReviewRequest(Contract):
    narrative: NarrativeDraft
    evidence: ApprovedEvidenceView
    requirements: ProjectRequirements
    runtime_capabilities: RuntimeCapabilities

    @model_validator(mode="after")
    def review_binding(self) -> Self:
        if (
            not (
                self.narrative.package.project_id
                == self.evidence.evidence.project_id
                == self.requirements.project_id
            )
            or self.narrative.package.evidence_package_hash != self.evidence.evidence_ref.sha256
        ):
            raise ValueError("Review input project/evidence mismatch")
        return self


class AssemblyRequest(Contract):
    evidence: ApprovedEvidenceView
    narrative: NarrativePackage
    narrative_ref: ArtifactRef
    reviews: ReviewSnapshot
    runtime_capabilities: RuntimeCapabilities

    @model_validator(mode="after")
    def approved_inputs(self) -> Self:
        ref = self.narrative_ref
        if (
            self.narrative.project_id != self.evidence.evidence.project_id
            or ref.project_id != self.narrative.project_id
            or ref.kind != "narrative"
            or ref.sha256 != CanonicalSerializer.digest(self.narrative)
            or ref.content_version != self.narrative.content_version
            or self.narrative.evidence_package_hash != self.evidence.evidence_ref.sha256
            or self.narrative.routes != (self.evidence.approved_route_ref,)
            or self.reviews.environment != self.evidence.reviews.environment
        ):
            raise ValueError("Assembly inputs mismatch")
        if not any(
            target.target_id == ref.artifact_id
            and target.version == ref.content_version
            and target.sha256 == ref.sha256
            and target.gate == "narrative"
            for target in self.reviews.required_targets
        ):
            raise ValueError("Narrative approval target missing")
        return self


class PackageValidationRequest(Contract):
    package: RuntimePackage
    runtime_capabilities: RuntimeCapabilities
    checks: tuple[
        Literal["schema", "references", "review_bindings", "media_hashes", "rule_paths"], ...
    ]

    @model_validator(mode="after")
    def runtime_binding(self) -> Self:
        unique(self.checks, "validation checks")
        if self.package.runtime_compatibility != self.runtime_capabilities:
            raise ValueError("Runtime capability mismatch")
        return self


class AssemblyResult(Contract):
    package: RuntimePackage
    report: ValidationReport

    @model_validator(mode="after")
    def report_binding(self) -> Self:
        if self.report.artifact_hash != CanonicalSerializer.digest(self.package):
            raise ValueError("Assembly report does not refer to the returned package")
        return self


class Usage(Contract):
    input_tokens: NonNegative
    output_tokens: NonNegative
    cost_microusd: NonNegative | None


class ModelResult[T: Contract](Contract):
    payload: T
    usage: Usage
    provider_request_id: Identifier | None
    finish: Literal["completed"]


class SourceDocument(Contract):
    source: Source
    fragments: tuple["LocatedText", ...]
    status: Literal["read", "inaccessible", "needs_ocr", "failed"]


class LocatedText(Contract):
    locator: "SourceLocator"
    text: Text


class ToolResult(Contract):
    request_id: Identifier
    status: Literal["ok", "empty", "inaccessible", "needs_ocr", "network_error", "denied"]
    source_refs: tuple[ArtifactRef, ...]
    reason: Text


SourceDocument.model_rebuild()
