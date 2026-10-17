"""Offline adapters for explicitly supplied authored content; no model generation is implied."""

import json
from pathlib import Path

from pydantic import JsonValue

from pastport.application.models import ServiceError
from pastport.application.resources import VerifiedResourceReader
from pastport.application.updates import updated
from pastport.domain.common import Contract
from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ResearchRequest,
    ReviseRequest,
)
from pastport.domain.resources import ResourceReference
from pastport.ports.modules import ExecutionContext
from pastport.ports.resources import ResourceReader


def project_payload(value: JsonValue, project_id: str) -> JsonValue:
    if isinstance(value, dict):
        return {
            name: project_id if name == "project_id" else project_payload(item, project_id)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [project_payload(item, project_id) for item in value]
    return value


class LocalContentFiles:
    def __init__(self, directory: Path, allow_synthetic: bool = False) -> None:
        self.directory = directory.resolve()
        self.allow_synthetic = allow_synthetic

    def read[Payload: Contract](self, name: str, model: type[Payload], project_id: str) -> Payload:
        try:
            raw: JsonValue = json.loads((self.directory / name).read_bytes())
        except (OSError, ValueError) as error:
            raise ServiceError(
                "FIXTURE_UNAVAILABLE", "Configured test fixture cannot be read", 503
            ) from error
        return model.model_validate_json(json.dumps(project_payload(raw, project_id)))


class LocalEvidenceAdapter:
    def __init__(self, content: LocalContentFiles, resources: ResourceReader | None = None) -> None:
        self.content = content
        self.resources = VerifiedResourceReader(resources) if resources is not None else None

    async def inventory(
        self, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        context.cancellation.raise_if_cancelled()
        if request.folder.provider != "local_manifest":
            raise ServiceError(
                "CAPABILITY_UNSUPPORTED", "Local adapter accepts local manifests only"
            )
        result = self.content.read(
            "inventory-result.json", ModuleResult[SourceManifestDraft], context.metadata.project_id
        )
        if result.payload is not None:
            if (
                not self.content.allow_synthetic
                and result.payload.source_folder_id != request.folder.folder_id
            ):
                raise ServiceError(
                    "SOURCE_FOLDER_MISMATCH", "Content belongs to another source folder"
                )
            if self.content.allow_synthetic:
                result = updated(
                    result,
                    payload=updated(result.payload, source_folder_id=request.folder.folder_id),
                )
            assert result.payload is not None
            for source in result.payload.sources:
                if source.origin == "synthetic" and not self.content.allow_synthetic:
                    raise ServiceError(
                        "SYNTHETIC_SOURCE_FORBIDDEN", "Synthetic sources require test mode"
                    )
                if self.resources is None:
                    continue
                self.resources.read(
                    ResourceReference(
                        project_id=context.metadata.project_id,
                        resource_id=source.source_id,
                        kind="source",
                        version=source.version,
                        sha256=source.file_sha256,
                        source_uri=source.uri,
                    ),
                    20 * 1024 * 1024,
                )
        return result

    async def index(
        self, request: IndexRequest, context: ExecutionContext
    ) -> ModuleResult[SourceIndexDraft]:
        context.cancellation.raise_if_cancelled()
        if request.manifest.project_id != context.metadata.project_id:
            raise ServiceError("PROJECT_MISMATCH", "Index request belongs to another project")
        return self.content.read(
            "index-result.json", ModuleResult[SourceIndexDraft], context.metadata.project_id
        )

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        context.cancellation.raise_if_cancelled()
        result = self.content.read(
            "research-result.json", ModuleResult[EvidenceFindings], context.metadata.project_id
        )
        if result.payload is None:
            return result
        candidate_id = request.evidence_request.candidate_id
        routes = (
            tuple(
                updated(route, candidate_id=candidate_id)
                for route in result.payload.route_candidates
            )
            if candidate_id is not None
            else ()
        )
        return updated(
            result,
            payload=updated(
                result.payload,
                request_id=request.evidence_request.request_id,
                route_candidates=routes,
            ),
        )


class LocalNarrativeAdapter:
    def __init__(self, content: LocalContentFiles) -> None:
        self.content = content

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        context.cancellation.raise_if_cancelled()
        if request.index.project_id != context.metadata.project_id:
            raise ServiceError("PROJECT_MISMATCH", "Discovery input belongs to another project")
        result = self.content.read(
            "discover-result.json", ModuleResult[CandidateSetDraft], context.metadata.project_id
        )
        if result.payload is None:
            return result
        index_ref = next(
            reference
            for reference in context.metadata.input_refs
            if reference.kind == "source_index"
        )
        candidates = tuple(
            updated(candidate, source_refs=(index_ref,)) for candidate in result.payload.candidates
        )
        return updated(result, payload=updated(result.payload, candidates=candidates))

    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        context.cancellation.raise_if_cancelled()
        result = self.content.read(
            "draft-result.json", ModuleResult[NarrativeDraft], context.metadata.project_id
        )
        if result.payload is None:
            return result
        package = updated(
            result.payload.package,
            evidence_package_hash=request.evidence.evidence_ref.sha256,
            candidate_id=request.selected_candidate.candidate_id,
            routes=(request.evidence.approved_route_ref,),
        )
        return updated(result, payload=updated(result.payload, package=package))

    async def revise(
        self, request: ReviseRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        context.cancellation.raise_if_cancelled()
        return ModuleResult[NarrativeDraft](
            outcome="blocked",
            payload=None,
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="This local adapter needs an authored replacement to revise a story.",
        )

    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]:
        context.cancellation.raise_if_cancelled()
        return ModuleResult[NarrativeReview](
            outcome="completed",
            payload=NarrativeReview(
                narrative_ref=next(
                    reference
                    for reference in context.metadata.input_refs
                    if reference.kind == "narrative"
                ),
                issues=(),
                counterexamples=("No model or player evaluation ran in test mode.",),
                human_review_required=True,
            ),
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="Offline interface review only; human approval remains required.",
        )
