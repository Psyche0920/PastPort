"""Shared services supplied to independently constructed content modules."""

from dataclasses import dataclass
from typing import Protocol

from pastport.domain.modules import EvidenceFindings
from pastport.domain.workflow import RemainingLimits, SkillResult
from pastport.ports.modules import (
    ExecutionContext,
    ModelGateway,
    ModelRequest,
    SourceReader,
    ToolExecutor,
)
from pastport.ports.story_inputs import MatchedEnvironmentReader


class ResearchExecutor(Protocol):
    async def run(
        self, request: ModelRequest[SkillResult[EvidenceFindings]], context: ExecutionContext
    ) -> SkillResult[EvidenceFindings]: ...


class UsageReader(Protocol):
    def remaining(self, context: ExecutionContext) -> RemainingLimits: ...


@dataclass(frozen=True, slots=True)
class ModuleServices:
    models: ModelGateway
    sources: SourceReader
    tools: ToolExecutor
    research: ResearchExecutor
    usage: UsageReader
    environment: MatchedEnvironmentReader | None = None
