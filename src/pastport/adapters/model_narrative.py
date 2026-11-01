"""Story Agent adapter backed by the shared, metered model gateway."""

from collections.abc import Iterable
from typing import Literal, cast

from pastport.application.models import ServiceError
from pastport.application.workflow_control import SkillResultMapper
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ReviseRequest,
)
from pastport.domain.workflow import SkillResult
from pastport.ports.execution import ModuleServices
from pastport.ports.modules import ExecutionContext, ModelRequest, NarrativePort


class ModelNarrativeAdapter(NarrativePort):
    """Generate narrative artifacts through the run's pinned Skill, model and budget."""

    def __init__(self, services: ModuleServices) -> None:
        self._services = services

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        index_ref = self._find_ref(
            context.metadata.input_refs,
            kind="source_index",
            digest=CanonicalSerializer.digest(request.index),
        )
        return await self._generate(
            CandidateSetDraft,
            (index_ref,),
            mode="discover",
            context=context,
        )

    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        refs = self._registered_refs(
            context,
            (
                request.selected_candidate.candidate_set_ref,
                request.evidence.evidence_ref,
                request.evidence.approved_route_ref,
            ),
        )
        return await self._generate(NarrativeDraft, refs, mode="draft", context=context)

    async def revise(
        self, request: ReviseRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        narrative_ref = self._find_ref(
            context.metadata.input_refs,
            kind="narrative",
            digest=CanonicalSerializer.digest(request.narrative.package),
        )
        refs = self._registered_refs(
            context,
            (
                request.draft_request.selected_candidate.candidate_set_ref,
                request.draft_request.evidence.evidence_ref,
                request.draft_request.evidence.approved_route_ref,
                narrative_ref,
            ),
        )
        return await self._generate(NarrativeDraft, refs, mode="revise", context=context)

    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]:
        narrative_ref = self._find_ref(
            context.metadata.input_refs,
            kind="narrative",
            digest=CanonicalSerializer.digest(request.narrative.package),
        )
        refs = self._registered_refs(
            context,
            (
                narrative_ref,
                request.evidence.evidence_ref,
                request.evidence.approved_route_ref,
            ),
        )
        return await self._generate(NarrativeReview, refs, mode="review", context=context)

    async def _generate[Payload: Contract](
        self,
        payload_type: type[Payload],
        refs: tuple[ArtifactRef, ...],
        mode: Literal["discover", "draft", "revise", "review"],
        context: ExecutionContext,
    ) -> ModuleResult[Payload]:
        context.cancellation.raise_if_cancelled()
        skill_ref = context.metadata.skill_ref
        if skill_ref is None or skill_ref.kind != "skill":
            raise ServiceError("MODEL_NOT_CONFIGURED", "Narrative Skill is not pinned", 503)
        if not refs or len(refs) > 32 or len(set(refs)) != len(refs):
            raise ServiceError("MODEL_INPUT_INVALID", "Narrative inputs are invalid", 422)

        result_type = cast(
            type[SkillResult[Payload]], SkillResult.__class_getitem__(payload_type)
        )
        result = await self._services.models.generate(
            ModelRequest(
                role="story",
                input_refs=refs,
                skill_ref=skill_ref,
                output_model=result_type,
            ),
            context,
        )
        context.cancellation.raise_if_cancelled()
        response = result.payload
        if (
            response.request_id != context.metadata.operation_id
            or response.skill != "narrative"
            or response.mode != mode
            or response.input_refs != refs
        ):
            raise ServiceError(
                "MODEL_OUTPUT_MISMATCH",
                "Narrative output does not match the pinned stage inputs",
                422,
            )
        module_type = cast(
            type[ModuleResult[Payload]], ModuleResult.__class_getitem__(payload_type)
        )
        return SkillResultMapper.to_module_result(response, module_type)

    @classmethod
    def _registered_refs(
        cls, context: ExecutionContext, refs: Iterable[ArtifactRef]
    ) -> tuple[ArtifactRef, ...]:
        return tuple(cls._find_ref(context.metadata.input_refs, ref=ref) for ref in refs)

    @staticmethod
    def _find_ref(
        refs: tuple[ArtifactRef, ...],
        *,
        kind: str | None = None,
        digest: str | None = None,
        ref: ArtifactRef | None = None,
    ) -> ArtifactRef:
        match = next(
            (
                item
                for item in refs
                if (kind is None or item.kind == kind)
                and (digest is None or item.sha256 == digest)
                and (ref is None or item == ref)
            ),
            None,
        )
        if match is None:
            raise ServiceError(
                "MODEL_INPUT_UNREGISTERED",
                "Narrative input is not pinned to this workflow run",
                409,
            )
        return match
