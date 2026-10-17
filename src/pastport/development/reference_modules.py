"""Independent, request-bound synthetic ports for the offline acceptance kit."""

from pathlib import Path

from pastport.application.updates import updated
from pastport.development.module_check import FixtureResults
from pastport.domain.evidence import SourceManifestDraft
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    EvidenceFindings,
    InventoryRequest,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ResearchRequest,
)
from pastport.ports.modules import EvidencePort, ExecutionContext, NarrativePort


class ReferenceEvidence(FixtureResults):
    """Adapt synthetic wire fixtures to the actual request identities."""

    async def inventory(
        self, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        result = await super().inventory(request, context)
        assert result.payload is not None
        return updated(
            result, payload=updated(result.payload, source_folder_id=request.folder.folder_id)
        )

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        result = await super().research(request, context)
        assert result.payload is not None
        return updated(
            result,
            payload=updated(
                result.payload,
                request_id=request.evidence_request.request_id,
                route_candidates=tuple(
                    updated(route, candidate_id=request.evidence_request.candidate_id)
                    for route in result.payload.route_candidates
                ),
            ),
        )


class ReferenceNarrative(FixtureResults):
    """Exercise a separate implementation without importing local adapter classes."""

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        result = await super().discover(request, context)
        assert result.payload is not None
        index_ref = next(
            item for item in context.metadata.input_refs if item.kind == "source_index"
        )
        return updated(
            result,
            payload=updated(
                result.payload,
                candidates=tuple(
                    updated(item, source_refs=(index_ref,)) for item in result.payload.candidates
                ),
            ),
        )

    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        result = await super().draft(request, context)
        assert result.payload is not None
        return updated(
            result,
            payload=updated(
                result.payload,
                package=updated(
                    result.payload.package,
                    evidence_package_hash=request.evidence.evidence_ref.sha256,
                    candidate_id=request.selected_candidate.candidate_id,
                    routes=(request.evidence.approved_route_ref,),
                ),
            ),
        )

    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]:
        result = await super().review(request, context)
        assert result.payload is not None
        reference = next(item for item in context.metadata.input_refs if item.kind == "narrative")
        return updated(result, payload=updated(result.payload, narrative_ref=reference))


def build_evidence(fixtures: Path) -> EvidencePort:
    return ReferenceEvidence(fixtures)


def build_narrative(fixtures: Path) -> NarrativePort:
    return ReferenceNarrative(fixtures)
