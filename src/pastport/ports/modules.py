"""Process-local boundaries. No SDK, database, retry loop or fake success lives here."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pastport.domain.common import ArtifactRef, Contract
from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
from pastport.domain.game import ActionRequest, ActionResult, PlayerState
from pastport.domain.modules import (
    AssemblyRequest,
    AssemblyResult,
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModelResult,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    PackageValidationRequest,
    ResearchRequest,
    ReviseRequest,
    SourceDocument,
    ToolResult,
)
from pastport.domain.packages import RuntimePackage, ValidationReport
from pastport.domain.workflow import ExecutionMetadata, ToolRequest


class Cancellation(Protocol):
    def raise_if_cancelled(self) -> None:
        """Raise the execution owner's cancellation exception without consuming budget."""
        ...


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    metadata: ExecutionMetadata
    cancellation: Cancellation


class EvidencePort(Protocol):
    async def inventory(
        self, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]: ...
    async def index(
        self, request: IndexRequest, context: ExecutionContext
    ) -> ModuleResult[SourceIndexDraft]: ...
    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]: ...


class NarrativePort(Protocol):
    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]: ...
    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]: ...
    async def revise(
        self, request: ReviseRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]: ...
    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]: ...


class AssemblyPort(Protocol):
    def assemble(self, request: AssemblyRequest) -> AssemblyResult: ...


class PackageValidatorPort(Protocol):
    def validate(self, request: PackageValidationRequest) -> ValidationReport: ...


class PlayerRuntimePort(Protocol):
    def initial_state(self, package: RuntimePackage, release_id: str) -> PlayerState: ...
    def apply_action(
        self, package: RuntimePackage, state: PlayerState, action: ActionRequest
    ) -> ActionResult: ...
    def validate_state(self, package: RuntimePackage, state: PlayerState) -> None: ...


@dataclass(frozen=True, slots=True)
class ModelRequest[T: Contract]:
    role: Literal["research", "story"]
    input_refs: tuple[ArtifactRef, ...]
    skill_ref: ArtifactRef
    output_model: type[T]


class ModelGateway(Protocol):
    async def generate[T: Contract](
        self, request: ModelRequest[T], context: ExecutionContext
    ) -> ModelResult[T]: ...


class SourceReader(Protocol):
    async def read(self, source_ref: ArtifactRef, context: ExecutionContext) -> SourceDocument: ...


class ToolExecutor(Protocol):
    async def execute(self, request: ToolRequest, context: ExecutionContext) -> ToolResult: ...
