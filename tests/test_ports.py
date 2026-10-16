"""Module substitution against typed fixtures, independent of providers or a workflow graph."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import (
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    ResearchRequest,
)
from pastport.domain.workflow import ExecutionMetadata
from pastport.ports.modules import EvidencePort, ExecutionContext

FIXTURES = Path(__file__).parent / "fixtures" / "reference"


class Cancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class TestCancellation:
    __test__ = False
    cancelled: bool

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise Cancelled("Cancelled before module work")


class FixtureEvidence:
    """Test adapter only; never registered as a production fallback."""

    async def inventory(
        self,
        request: InventoryRequest,
        context: ExecutionContext,
    ) -> ModuleResult[SourceManifestDraft]:
        context.cancellation.raise_if_cancelled()
        assert request.requirements.project_id == context.metadata.project_id
        return ModuleResult[SourceManifestDraft].model_validate_json(
            (FIXTURES / "inventory-result.json").read_bytes(),
        )

    async def index(
        self,
        request: IndexRequest,
        context: ExecutionContext,
    ) -> ModuleResult[SourceIndexDraft]:
        context.cancellation.raise_if_cancelled()
        assert request.manifest.project_id == context.metadata.project_id
        return ModuleResult[SourceIndexDraft].model_validate_json(
            (FIXTURES / "index-result.json").read_bytes(),
        )

    async def research(
        self,
        request: ResearchRequest,
        context: ExecutionContext,
    ) -> ModuleResult[EvidenceFindings]:
        context.cancellation.raise_if_cancelled()
        assert request.index.project_id == context.metadata.project_id
        return ModuleResult[EvidenceFindings].model_validate_json(
            (FIXTURES / "research-result.json").read_bytes(),
        )


def context(cancelled: bool = False) -> ExecutionContext:
    return ExecutionContext(
        ExecutionMetadata.model_validate_json((FIXTURES / "execution-metadata.json").read_bytes()),
        TestCancellation(cancelled),
    )


async def consume(port: EvidencePort, ctx: ExecutionContext) -> tuple[str, ...]:
    inventory = await port.inventory(
        InventoryRequest.model_validate_json((FIXTURES / "inventory-request.json").read_bytes()),
        ctx,
    )
    index = await port.index(
        IndexRequest.model_validate_json((FIXTURES / "index-request.json").read_bytes()),
        ctx,
    )
    research = await port.research(
        ResearchRequest.model_validate_json((FIXTURES / "research-request.json").read_bytes()),
        ctx,
    )
    assert inventory.payload and index.payload and research.payload
    return tuple(x.project_id for x in (inventory.payload, index.payload, research.payload))


def test_independent_evidence_adapter_obeys_port() -> None:
    port: EvidencePort = FixtureEvidence()
    assert asyncio.run(consume(port, context())) == ("fixture-project",) * 3


def test_cancellation_is_not_converted_into_success() -> None:
    with pytest.raises(Cancelled):
        asyncio.run(consume(FixtureEvidence(), context(cancelled=True)))
