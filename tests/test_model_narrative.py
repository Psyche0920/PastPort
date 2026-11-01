"""Metered Story Agent adapter tests using deterministic local fixtures."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pytest

from pastport.adapters.model_narrative import ModelNarrativeAdapter
from pastport.application.models import ServiceError
from pastport.domain.common import ArtifactKind, ArtifactRef, CanonicalSerializer, Contract
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    ModelResult,
    ModuleResult,
    NarrativeDraft,
    Usage,
)
from pastport.domain.workflow import ExecutionMetadata, RemainingLimits, SkillResult
from pastport.ports.execution import ModuleServices, ResearchExecutor, UsageReader
from pastport.ports.modules import ExecutionContext, ModelRequest, SourceReader, ToolExecutor

FIXTURES = Path(__file__).parent / "fixtures" / "reference"
PROJECT_ID = "fixture-project"
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class NoCancellation:
    def raise_if_cancelled(self) -> None:
        return None


class RecordingModelGateway:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests: list[ModelRequest[Contract]] = []

    async def generate[Payload: Contract](
        self, request: ModelRequest[Payload], context: ExecutionContext
    ) -> ModelResult[Payload]:
        del context
        self.requests.append(cast(ModelRequest[Contract], request))
        assert isinstance(self.payload, request.output_model)
        result_type = cast(
            type[ModelResult[Payload]], ModelResult.__class_getitem__(request.output_model)
        )
        return result_type(
            payload=self.payload,
            usage=Usage(input_tokens=1, output_tokens=1, cost_microusd=1),
            provider_request_id="fixture-request",
            finish="completed",
        )


def artifact(kind: ArtifactKind, name: str, payload: Contract | None = None) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        project_id=PROJECT_ID,
        kind=kind,
        schema_version="0.1.0",
        content_version="1",
        sha256=CanonicalSerializer.digest(payload) if payload is not None else "a" * 64,
    )


def context(refs: tuple[ArtifactRef, ...]) -> ExecutionContext:
    metadata = ExecutionMetadata(
        project_id=PROJECT_ID,
        run_id="run-model-story",
        operation_id="operation-model-story",
        execution_key="b" * 64,
        input_refs=refs,
        policy_ref=artifact("policy", "policy"),
        skill_ref=artifact("skill", "narrative"),
        model_config_ref=artifact("model_config", "model-story"),
        budget_reservation_id="budget",
        actor_id="editor",
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        remaining_limits=RemainingLimits(
            model_requests=1,
            input_tokens=10000,
            output_tokens=5000,
            search_requests=0,
            fetch_requests=0,
            active_seconds=60,
            cost_microusd=100000,
        ),
        allowed_tools=(),
    )
    return ExecutionContext(metadata, NoCancellation())


def services(gateway: RecordingModelGateway) -> ModuleServices:
    return ModuleServices(
        models=gateway,
        sources=cast(SourceReader, object()),
        tools=cast(ToolExecutor, object()),
        research=cast(ResearchExecutor, object()),
        usage=cast(UsageReader, object()),
    )


def skill_result[Payload: Contract](
    *, mode: Literal["discover", "draft"], refs: tuple[ArtifactRef, ...], payload: Payload
) -> SkillResult[Payload]:
    result_type = cast(type[SkillResult[Payload]], SkillResult.__class_getitem__(type(payload)))
    return result_type(
        request_id="operation-model-story",
        skill="narrative",
        mode=mode,
        input_refs=refs,
        decision="complete",
        reason_code="GENERATED",
        reason="Generated through the shared model port",
        payload=payload,
        issues=(),
        changed_ids=(),
        evidence_requests=(),
        tool_request=None,
    )


async def test_discover_pins_registered_source_index() -> None:
    request = DiscoverRequest.model_validate_json((FIXTURES / "discover-request.json").read_bytes())
    result = ModuleResult[CandidateSetDraft].model_validate_json(
        (FIXTURES / "discover-result.json").read_bytes()
    )
    assert result.payload is not None
    refs = (artifact("source_index", "index", request.index),)
    gateway = RecordingModelGateway(
        skill_result(mode="discover", refs=refs, payload=result.payload)
    )
    adapter = ModelNarrativeAdapter(services(gateway))

    output = await adapter.discover(request, context(refs))

    assert output.outcome == "completed"
    assert output.payload == result.payload
    assert len(gateway.requests) == 1
    assert gateway.requests[0].role == "story"
    assert gateway.requests[0].input_refs == refs


async def test_draft_pins_selected_direction_and_approved_evidence() -> None:
    request = DraftRequest.model_validate_json((FIXTURES / "draft-request.json").read_bytes())
    result = ModuleResult[NarrativeDraft].model_validate_json(
        (FIXTURES / "draft-result.json").read_bytes()
    )
    assert result.payload is not None
    refs = (
        request.selected_candidate.candidate_set_ref,
        request.evidence.evidence_ref,
        request.evidence.approved_route_ref,
    )
    gateway = RecordingModelGateway(skill_result(mode="draft", refs=refs, payload=result.payload))
    adapter = ModelNarrativeAdapter(services(gateway))

    output = await adapter.draft(request, context(refs))

    assert output.outcome == "completed"
    assert output.payload == result.payload
    assert gateway.requests[0].input_refs == refs
    assert gateway.requests[0].output_model == SkillResult[NarrativeDraft]


async def test_mismatched_stage_result_is_rejected() -> None:
    request = DiscoverRequest.model_validate_json((FIXTURES / "discover-request.json").read_bytes())
    result = ModuleResult[CandidateSetDraft].model_validate_json(
        (FIXTURES / "discover-result.json").read_bytes()
    )
    assert result.payload is not None
    refs = (artifact("source_index", "index", request.index),)
    gateway = RecordingModelGateway(skill_result(mode="draft", refs=refs, payload=result.payload))
    adapter = ModelNarrativeAdapter(services(gateway))

    try:
        await adapter.discover(request, context(refs))
    except ServiceError as error:
        assert error.code == "MODEL_OUTPUT_MISMATCH"
    else:
        raise AssertionError("Mismatched Story Skill output must be rejected")
