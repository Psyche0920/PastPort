"""Composition root for grants, provider configuration and services given to module factories."""

from pathlib import Path

from pastport.adapters.skills import SkillLoader
from pastport.application.execution_guard import ExecutionGuard
from pastport.application.execution_models import (
    ExecutionBinding,
    ExecutionSettings,
    ProviderRegistration,
)
from pastport.application.model_gateway import SharedModelGateway
from pastport.application.models import LocalExecutionPolicy, RunRecord
from pastport.application.reliability import ReviewAuthority
from pastport.application.research_execution import SharedResearchExecutor
from pastport.application.source_tools import SharedSourceReader, SharedToolExecutor
from pastport.application.updates import updated
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.workflow import ExecutionMetadata, RemainingLimits
from pastport.ports.editorial import EditorialRepository
from pastport.ports.execution import ModuleServices
from pastport.ports.resources import ResourceReader


class ExecutionRuntime:
    def __init__(
        self,
        database: EditorialRepository,
        settings: ExecutionSettings,
        skill_directory: Path,
        providers: tuple[ProviderRegistration, ...],
        resources: ResourceReader | None,
        authority: ReviewAuthority,
        environment: str,
    ) -> None:
        if environment != "test" and any(m.provider == "fake" for m in settings.models):
            raise ValueError("Fake model providers require an explicit test environment")
        if len({p.name for p in providers}) != len(providers):
            raise ValueError("Providers must have unique registered identities")
        loader = SkillLoader(skill_directory)
        binding = ExecutionBinding(
            settings=settings, skills=tuple(loader.load(m) for m in settings.models)
        )
        self.guard = ExecutionGuard(database, binding, authority)
        self.settings = settings
        self.policy = LocalExecutionPolicy(
            environment="test" if environment == "test" else "production",
            external_model_calls=any(m.provider == "openai" for m in settings.models),
            external_tools=settings.allowed_tools,
            execution_config_hash=self.guard.binding_hash,
        )
        models = SharedModelGateway(self.guard, {p.name: p.provider for p in providers}, loader)
        sources = SharedSourceReader(self.guard, resources)
        tools = SharedToolExecutor(self.guard, sources)
        self.services = ModuleServices(
            models, sources, tools, SharedResearchExecutor(self.guard, models, tools), self.guard
        )

    def context(self, run: RunRecord, metadata: ExecutionMetadata) -> ExecutionMetadata:
        role = (
            "research" if run.state.node in ("extract_candidates", "research_evidence") else "story"
        )
        policy = next((m for m in self.settings.models if m.role == role), None)
        if run.state.node not in (
            "extract_candidates",
            "research_evidence",
            "discover_story",
            "draft_narrative",
        ):
            policy = None
        skill_ref = model_ref = None
        if policy is not None:
            bundle = next(
                b
                for b in self.guard.binding.skills
                if b.name == ("evidence-review" if role == "research" else "narrative")
            )
            skill_ref = ArtifactRef(
                artifact_id=bundle.name,
                project_id=run.state.project_id,
                kind="skill",
                schema_version="0.1.0",
                content_version=bundle.version,
                sha256=CanonicalSerializer.digest(bundle),
            )
            model_ref = ArtifactRef(
                artifact_id="model-" + role,
                project_id=run.state.project_id,
                kind="model_config",
                schema_version="0.1.0",
                content_version=policy.price_version,
                sha256=CanonicalSerializer.digest(policy),
            )
        snapshot = self.guard.database.budget(run.state.run_id)

        def left(field: str) -> int:
            return max(
                0,
                int(getattr(snapshot.limit, field))
                - int(getattr(snapshot.used, field))
                - int(getattr(snapshot.held, field)),
            )

        return updated(
            metadata,
            skill_ref=skill_ref,
            model_config_ref=model_ref,
            allowed_tools=self.settings.allowed_tools
            if run.state.node == "research_evidence"
            else (),
            remaining_limits=RemainingLimits(
                model_requests=left("model_requests") if policy else 0,
                input_tokens=left("input_tokens") if policy else 0,
                output_tokens=left("output_tokens") if policy else 0,
                search_requests=left("search_requests")
                if run.state.node == "research_evidence"
                else 0,
                fetch_requests=left("fetch_requests")
                if run.state.node == "research_evidence"
                else 0,
                cost_microusd=left("cost_microusd") if policy else 0,
                active_seconds=metadata.remaining_limits.active_seconds,
            ),
        )
