"""Run the existing metered editorial graph up to its Story output boundary."""

import asyncio
import hashlib
import json
import secrets
from importlib.resources import files
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import JsonValue, TypeAdapter, ValidationError

from pastport.adapters.codex_provider import CodexStoryProvider
from pastport.adapters.database import EditorialDatabase
from pastport.adapters.gameplay_catalog import load_gameplay_catalog
from pastport.adapters.model_narrative import ModelNarrativeAdapter
from pastport.adapters.story_materials import StoryMaterialReader, StoryMaterials
from pastport.api.app import create_app
from pastport.api.settings import AppSettings, Credential
from pastport.application.execution_models import (
    ExecutionSettings,
    ModelPolicy,
    ModelProvider,
    ProviderRegistration,
    ProviderRequest,
    ProviderResponse,
)
from pastport.application.models import (
    Actor,
    CreateProject,
    CreateRun,
    ReviewChoice,
    RunCommand,
    RunRecord,
    SelectCandidate,
    ServiceError,
    SubmitReview,
)
from pastport.application.story_authoring import StoryDraftInspector, StoryInputLock
from pastport.domain.common import (
    ArtifactRef,
    CanonicalSerializer,
    Contract,
    ProjectRequirements,
    SourceLocator,
)
from pastport.domain.evidence import Place, RouteRecord, SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import (
    CandidateScore,
    CandidateSetDraft,
    DiscoverRequest,
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    NarrativeDraft,
    ResearchRequest,
    StoryCandidate,
)
from pastport.domain.workflow import BudgetPolicy
from pastport.ports.modules import ExecutionContext


class StoryEvidenceAdapter:
    def __init__(self, materials: StoryMaterials) -> None:
        self.materials = materials

    async def inventory(
        self, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        context.cancellation.raise_if_cancelled()
        return ModuleResult[SourceManifestDraft](
            outcome="completed",
            payload=self.materials.manifest,
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="Registered upstream inputs read without rematching",
        )

    async def index(
        self, request: IndexRequest, context: ExecutionContext
    ) -> ModuleResult[SourceIndexDraft]:
        context.cancellation.raise_if_cancelled()
        return ModuleResult[SourceIndexDraft](
            outcome="completed",
            payload=self.materials.index,
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="Page-located original source and candidate quotes",
        )

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        context.cancellation.raise_if_cancelled()
        selected = request.selected_candidate
        if selected is None:
            raise ServiceError(
                "STORY_SCOPE_MISSING", "Private authoring needs its registered scope"
            )
        museum = self.materials.museum
        locator = SourceLocator(
            source_id="environment-snapshot",
            source_version="1",
            file_sha256=self.materials.environment_sha256,
            page_index=None,
            printed_page=None,
            paragraph_or_region=(
                "Registered virtual viewpoints and directed links; not a surveyed historical route"
            ),
        )
        route = RouteRecord(
            project_id=museum.project_id,
            schema_version="0.1.0",
            content_version="1",
            route_id="registered-virtual-tour",
            candidate_id=selected.candidate_id,
            scope_hash=selected.requirements_ref.sha256,
            ordered_places=(Place(site_id=museum.environment_id, building_id=None),),
            edge_refs=(),
            entry_refs=(locator,),
            exit_refs=(locator,),
            source_refs=(locator,),
            unknowns=(),
        )
        findings = EvidenceFindings(
            project_id=museum.project_id,
            schema_version="0.1.0",
            content_version="1",
            request_id=request.evidence_request.request_id,
            sources=self.materials.index.sources,
            claims=self.materials.index.candidate_claims,
            assets=self.materials.index.candidate_assets,
            route_candidates=(route,),
            index=self.materials.index,
            unresolved_items=(
                *self.materials.index.unresolved_items,
                "Metric calibration and physical interaction approval are not inferred. "
                "The registered single-site virtual tour is not a surveyed historical route.",
            ),
        )
        return ModuleResult[EvidenceFindings](
            outcome="completed",
            payload=findings,
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="Source-attributed private evidence, not human approval",
        )


class StoryScopeNarrative(ModelNarrativeAdapter):
    """One source-scope seed enables one true model draft; it is not a discovered plot."""

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        context.cancellation.raise_if_cancelled()
        reference = next(ref for ref in context.metadata.input_refs if ref.kind == "source_index")
        dimensions: tuple[
            Literal["evidence", "visual", "character", "solvability", "spatial"], ...
        ] = (
            "evidence",
            "visual",
            "character",
            "solvability",
            "spatial",
        )
        candidate = StoryCandidate(
            candidate_id="source-bound-private-story",
            premise=request.requirements.theme_brief,
            source_refs=(reference,),
            supported_opportunities=("Use the registered source and object capabilities",),
            blocking_gaps=(),
            proposed_player_actions=("Author actions justified by actual source and space",),
            human_work_estimate_minutes=None,
            dimension_scores=tuple(
                CandidateScore(
                    dimension=dimension,
                    score=0,
                    reason=(
                        "Not evaluated; this is a host-selected authoring scope, not a "
                        "quality rating"
                    ),
                )
                for dimension in dimensions
            ),
            recommendation_reason="Owner-authorized direct private draft within the supplied scope",
            reversal_conditions=("Source bindings or scope change",),
        )
        result = CandidateSetDraft(
            project_id=request.requirements.project_id,
            schema_version="0.1.0",
            content_version="1",
            candidates=(candidate,),
            unresolved_items=(
                "Scope seed only; no model discovery or quality selection is claimed.",
            ),
        )
        return ModuleResult[CandidateSetDraft](
            outcome="completed",
            payload=result,
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="Direct authoring scope; the plot is generated in draft",
        )


class SavedResponseOnlyProvider:
    async def respond(self, request: ProviderRequest, timeout_seconds: float) -> ProviderResponse:
        raise ServiceError("SAVED_RESPONSE_MISSING", "Revalidation cannot make model calls")


class StoryAutomationWorkflow:
    def __init__(
        self,
        materials: StoryMaterials,
        output: Path,
        skills: Path,
        brief: str,
        provider: ModelProvider | None = None,
        revalidate_saved_response: bool = False,
        structure_profile: Literal[
            "authored_graph", "compiled_plan_v1", "compiled_branch_v1"
        ] = "compiled_plan_v1",
    ) -> None:
        self.materials, self.output, self.skills, self.brief = materials, output, skills, brief
        self.provider = provider
        self.revalidate_saved_response = revalidate_saved_response
        self.structure_profile = structure_profile

    def save(self, name: str, value: Contract) -> None:
        temporary = self.output / (name + ".tmp")
        temporary.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.output / name)

    def export_receipts(self, run_id: str) -> None:
        """Export original settled responses without making any provider call."""
        repository = EditorialDatabase(self.output / "application/editorial.sqlite3")
        directory = self.output / "receipts"
        directory.mkdir(exist_ok=True)
        for index, summary in enumerate(repository.execution_summaries(run_id)):
            receipt = repository.execution_receipt(summary.operation_id)
            if receipt is None:
                continue
            (directory / f"{index:02d}.json").write_text(
                receipt.model_dump_json(indent=2), encoding="utf-8"
            )
            response = receipt.response
            if response is None or not response.output_text:
                continue
            try:
                from pastport.application.preview_normalization import PreviewOutputNormalizer
                from pastport.domain.story_plan import BranchStoryPlanResult, StoryPlanResult
                from pastport.domain.workflow import SkillResult

                wire = TypeAdapter(dict[str, JsonValue]).validate_json(response.output_text)
                if "plan" in wire:
                    saved_plan = wire.get("plan")
                    (
                        BranchStoryPlanResult
                        if isinstance(saved_plan, dict)
                        and saved_plan.get("structure") == "compiled_branch_v1"
                        else StoryPlanResult
                    ).model_validate_json(response.output_text)
                    continue
                normalized = PreviewOutputNormalizer.normalize(response.output_text)
                (directory / f"{index:02d}-normalization.json").write_text(
                    normalized.model_dump_json(indent=2), encoding="utf-8"
                )
                SkillResult[NarrativeDraft].model_validate_json(normalized.output_text)
            except ValidationError as error:
                (directory / f"{index:02d}-validation.txt").write_text(str(error), encoding="utf-8")
            except ValueError as error:
                (directory / f"{index:02d}-validation.txt").write_text(
                    f"Response cannot be normalized: {error}", encoding="utf-8"
                )

    async def run(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        skill = (self.skills / "narrative/SKILL.md").read_bytes()
        previous_lock = self.output / "input-lock.json"
        structure = (
            StoryInputLock.model_validate_json(previous_lock.read_bytes()).structure_profile
            if previous_lock.exists()
            else self.structure_profile
        )
        compiler_hash = None
        if structure in ("compiled_plan_v1", "compiled_branch_v1"):
            digest = hashlib.sha256()
            for name in (
                "domain/story_plan.py",
                "application/story_compiler.py",
                "application/story_plan_schema.py",
                "application/story_branch_compiler.py",
            ):
                digest.update(name.encode() + b"\0" + files("pastport").joinpath(name).read_bytes())
            compiler_hash = digest.hexdigest()
        lock = StoryInputLock(
            structure_profile=structure,
            compiler_sha256=compiler_hash,
            project_id=self.materials.museum.project_id,
            original_pdf_sha256=self.materials.original_pdf_sha256,
            source_document_sha256=self.materials.source_document_sha256,
            environment_sha256=self.materials.environment_sha256,
            skill_sha256=hashlib.sha256(skill).hexdigest(),
            capability_catalog_sha256=load_gameplay_catalog().sha256,
            brief=self.brief,
            model="test" if self.provider is not None else CodexStoryProvider.MODEL,
            timeout_seconds=240,
            reasoning_effort="medium" if self.provider is not None else "high",
            source_index_sha256=CanonicalSerializer.digest(self.materials.index),
        )
        lock_path = self.output / "input-lock.json"
        if (
            lock_path.exists()
            and StoryInputLock.model_validate_json(lock_path.read_bytes()) != lock
        ):
            raise ServiceError(
                "STORY_INPUT_CHANGED", "Use a new output directory for changed inputs or Skill"
            )
        self.save("input-lock.json", lock)
        # The lock binds source bytes, not a re-serialization of the parsed DTO.
        original_environment = self.materials.environment_bytes
        if hashlib.sha256(original_environment).hexdigest() != lock.environment_sha256:
            raise ServiceError(
                "STORY_ENVIRONMENT_BYTES_CHANGED", "Registered environment bytes changed"
            )
        environment_file = self.output / "environment-input.json"
        if environment_file.exists() and environment_file.read_bytes() != original_environment:
            previous = environment_file.read_bytes()
            parsed = type(self.materials.museum).model_validate_json(previous)
            if CanonicalSerializer.digest(parsed) != CanonicalSerializer.digest(
                self.materials.museum
            ):
                raise ServiceError("STORY_ENVIRONMENT_CHANGED", "Saved environment content changed")
            previous_hash = hashlib.sha256(previous).hexdigest()
            backup = self.output / ("environment-input-serialization-" + previous_hash + ".json")
            if not backup.exists():
                backup.write_bytes(previous)
            (self.output / "environment-serialization-receipt.json").write_text(
                json.dumps(
                    {
                        "previous_sha256": previous_hash,
                        "registered_sha256": lock.environment_sha256,
                        "semantic_content_unchanged": True,
                        "new_model_calls": 0,
                    },
                    indent=2,
                )
            )
        environment_file.write_bytes(original_environment)
        self.save("source-index.json", self.materials.index)
        token = secrets.token_urlsafe(40)
        actor = Actor(
            actor_id="story-private-automation",
            roles=("editor", "evidence", "narrative", "operator"),
            project_ids=(lock.project_id,),
        )
        provider_name: Literal["fake", "codex"] = "fake" if self.provider is not None else "codex"
        policy = ModelPolicy(
            role="story",
            provider=provider_name,
            model="test" if provider_name == "fake" else CodexStoryProvider.MODEL,
            price_version=("private-story-quota-v1" if self.provider is not None else "private-story-quota-high-v2"),
            input_microusd_per_million=0,
            output_microusd_per_million=0,
            maximum_input_tokens=600000,
            maximum_output_tokens=16000,
        )
        prompt_museum = TypeAdapter(dict[str, JsonValue]).validate_json(
            StoryMaterialReader.spatial_context(self.materials)
        )
        objects = prompt_museum.get("objects")
        if isinstance(objects, list):
            for obj in objects:
                if isinstance(obj, dict):
                    # Narrative chooses object-N; authoritative UUID binding is read by code.
                    obj.pop("stable_id", None)
        context = json.dumps(
            {
                "gameplay_capabilities": load_gameplay_catalog().model_dump(mode="json"),
                "capability_catalog_sha256": load_gameplay_catalog().sha256,
                "page_text": [f.model_dump(mode="json") for f in self.materials.index.fragments],
                "museum": prompt_museum,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        constraints = (
            (
                "PRIVATE STORY ONLY. Retain unverified status; do not approve "
                "history or publish. Generate an original story and task "
                "semantics, no UI, plugins, assets or packaging code."
            ),
            (
                "Make the opening goal understandable in two short lines. Keep "
                "dialogue short and actionable; optional background belongs in the "
                "author report. Tasks must use specific heritage properties and "
                "actual object/view opportunities. Do not reuse an earlier story. "
                "Avoid treating modern proxies as ancient objects or mixing "
                "historical periods."
            ),
            (
                "Before drafting tasks, read the complete supplied PDF text and establish the "
                "setting, central mystery, character stakes and causal arc. Distinguish documented "
                "facts, catalog fiction and new fictional events. Ground every pivotal factual "
                "inference in an identifiable PDF passage and the corresponding museum object. "
                "Use the complete exhibit introduction for context, not a clipped citation as speech. "
                "Open with a concrete question, let each important clue change the player's "
                "interpretation, and make the resolution follow from clues already available. "
                "Write concise, natural exchanges with distinct voices and motives. Each pivotal "
                "exchange should reveal something, raise stakes or change a choice. Choose clue "
                "order for dramatic causality within a shared room. Check reachability and valid "
                "stations, and require travel only when the story or actual scene transition needs it. "
                "Use only mechanics the supplied capability catalog supports. Before returning, "
                "revise any clipped dialogue, unsupported inference, unearned reveal, unavailable "
                "clue or action the runtime cannot execute."
            ),
            (
                "Return SkillResult[NarrativeDraft]. Include spatial_intents with exactly "
                "one entry per task: task_id, object_number, view_id, station_id=spawn, "
                "interaction=inspect_linked_source. Select exact IDs from museum.metric_spatial; "
                "use only registered source-inspection stations and connected views. "
                "Scene prose must agree with those choices. Set capability_catalog_sha256 "
                "to the supplied catalog hash. Design tasks within its verified interfaces. "
                "Every task must have exactly one gameplay_intent in gameplay_intents. "
                "Reading declares kind=source_reading, task_id, capability_id=source-reading:1. "
                "Coverage declares kind=coverage, task_id, capability_id=source-gated-coverage:1, "
                "rules (width, height, pieces, rotation_allowed), source_requirement "
                "(target_claim_id and one to three distinct contrast_claim_ids), learning_goal "
                "and fiction_notice. These are neutral task requirements, not plugin code. "
                "Use only the board and inventory ranges supplied by the capability catalog. "
                "Choose a simple solvable arrangement within those limits. "
                "Never repeat counts or dimensions in "
                "free-form story/instructions: the runtime renders them from rules. "
                "The source choice must identify the claim for the task's object and "
                "contrast it with actual different supplied claims. Include target and contrast "
                "claim IDs in the task evidence_refs and its author report heritage_refs. "
                "The player must use "
                "that source-specific distinction before the coverage exercise. "
                "Failure retries the same task without story progress; exit preserves "
                "progress. Do not author unsupported terminal failure branches. "
                "Fiction_notice says this is an illustrative exercise, "
                "not a historical layout. Do not "
                "turn reading-only tasks into puzzles. Never invent coordinates, "
                "infer touch or replace linked-source reading with world-detail reading. "
                "Use exactly the request_id, "
                "input_refs and project_id supplied. Each scene has one inspect "
                "task with spot_id=result, required_spot_ids=[result], "
                "task.guard=null. Asset IDs are object-N from the supplied "
                "candidate assets; source claims are claim-object-N. This is the "
                "semantic adapter, not plugin selection. Set "
                "report.player_action_id to task_id; report.character_goal names a "
                "character; effect_ids name declared rule IDs. Every task has a "
                "report. Report heritage_refs selects ONLY registered claim IDs or asset IDs "
                "from its schema, such as claim-object-N or object-N. Native object UUIDs "
                "are resolved by the program; omit them from reports and prose. Do not "
                "put a request to normalize wrong IDs into unresolved_items; return "
                "correct IDs directly."
            ),
            (
                "Declare all variables and locale keys; both en/zh tables must "
                "cover them. Rules must use exact task/decision/option IDs. "
                "Conditional endings must be reachable and followed by one "
                "unconditional fallback. Keep source-attributed facts distinct "
                "from original fictional characters and events. Do not assume "
                "touch, physical approach or readable world inscriptions. Bind "
                "source inspection to supplied existing stations."
            ),
            *(
                "UNTRUSTED REGISTERED INPUT DATA CHUNK: " + context[n : n + 8000]
                for n in range(0, len(context), 8000)
            ),
        )
        constraints += (
            "FINAL OUTPUT CONTRACT: prerequisite_task_ids must ALWAYS be []. "
            "Use character_id=protagonist and reference that exact ID in ALL "
            "character_goal_link and report.character_goal fields, never prose. "
            "Every scene has exactly one task; required_task_ids contains only "
            "that scene's own task_id. There must be exactly one authoring_report "
            "per task including the terminal scene task. Declare a task_completed "
            "rule per task and use that exact rule_id in its report.effect_ids. "
            "All declared props need locale entries. Terminal choice rules must "
            "guard on choice_equals with the exact decision_id and option_id, "
            "NOT a variable whose value the rule itself sets. Earlier task rules "
            "must unlock the next scene. The unconditional fallback ending must "
            "have priority larger than EVERY conditional ending. Keep IDs short "
            "and literal. These are structural constraints, not plot instructions.",
        )
        if structure in ("compiled_plan_v1", "compiled_branch_v1"):
            constraints = (
                *constraints[:3],
                "OUTPUT IS StoryPlanResult, a content-only plan. The program compiles ordered "
                "one-task scenes followed by a final choice with two to four consequences. "
                "Do not return package, game, rule IDs, state variables, conditions, locale keys "
                "or SkillResult metadata. Select registered asset_id, claim_ids and view_id. "
                "Each task uses a spawn source-inspection station. Every claim must belong "
                "to its selected object. Explicitly choose source_reading or coverage from the "
                "supplied capability catalog. Coverage must include its exact supported rules "
                "and a source_requirement using actual target and contrast claims. Preserve "
                "quantities consistently in text. Supply bilingual dialogue, objectives, feedback "
                "and choice consequences; the compiler preserves them without rewriting. "
                "Write each dialogue locale as a multi-turn exchange, one turn per line, "
                "using 'Speaker: complete spoken sentence' with the actual speaker's name. "
                "Keep both locales aligned in turn order. Give each exchange at least two "
                "distinct speakers and use complete sentences rather than evidence excerpts. "
                "Each task's feedback states its visible narrative consequence. Final choices "
                "must differ meaningfully in consequences. Keep unsupported movement/detail/touch "
                "unknown; do not fabricate facts. If no feasible plan exists, return "
                "decision=no_feasible_story with plan=null and explain the limitation.",
                *(
                    "UNTRUSTED REGISTERED INPUT DATA CHUNK: " + context[n : n + 8000]
                    for n in range(0, len(context), 8000)
                ),
            )
        if structure == "compiled_branch_v1":
            constraints = (
                *constraints[:2],
                "OUTPUT IS BranchStoryPlanResult. Supply opening (1-3 tasks), investigations "
                "(2-4 exclusive routes, 1-3 tasks each), reunion (1-3 tasks), and 2-4 "
                "final choices. "
                "Each investigation has a bilingual label, fictional notebook "
                "finding, reunion_feedback "
                "and ending_consequences in the exact final-choice order. Routes must "
                "have different "
                "investigative actions or evidence access, not paraphrased identical scenes. "
                "Keep facts fixed; vary cooperation and obtainable information. "
                "Findings are original "
                "fiction, never historical approval. Tasks select registered assets, "
                "claims and views "
                "with honest source-based reasoning and supported source_reading or "
                "coverage gameplay. "
                "No runtime IDs, variables, conditions or SkillResult envelope. The compiler owns "
                "progression and carries the chosen route and finding through the "
                "reunion and ending. "
                "No nested forks, cross-route visits or arbitrary flag logic in this "
                "bounded profile. "
                "If the request needs unsupported mechanics, return no_feasible_story "
                "with plan=null.",
                *(
                    "UNTRUSTED REGISTERED INPUT DATA CHUNK: " + context[n : n + 8000]
                    for n in range(0, len(context), 8000)
                ),
            )
        settings = AppSettings(
            story_structure=structure,
            data_directory=self.output / "application",
            accounts=(
                Credential(token_sha256=hashlib.sha256(token.encode()).hexdigest(), actor=actor),
            ),
            environment="test" if self.provider is not None else "production",
            skill_directory=self.skills,
            execution=ExecutionSettings(models=(policy,), timeout_seconds=240),
            story_host_constraints=constraints,
        )
        app = create_app(
            settings,
            evidence=StoryEvidenceAdapter(self.materials),
            narrative_factory=StoryScopeNarrative,
            providers=(
                ProviderRegistration(
                    provider_name,
                    SavedResponseOnlyProvider()
                    if self.revalidate_saved_response
                    else self.provider
                    or CodexStoryProvider(trace_directory=self.output / "provider-traces"),
                ),
            ),
        )
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://story.local"
            ) as client:

                async def get(path: str) -> httpx.Response:
                    response = await client.get(path, headers=headers)
                    response.raise_for_status()
                    return response

                async def post(path: str, payload: Contract) -> httpx.Response:
                    response = await client.post(
                        path,
                        headers=headers | {"Idempotency-Key": str(uuid4())},
                        content=payload.model_dump_json(),
                    )
                    response.raise_for_status()
                    return response

                ref_file = self.output / "run-id.txt"
                revalidation_started = False
                if self.revalidate_saved_response and not ref_file.exists():
                    raise ServiceError("SAVED_RESPONSE_MISSING", "No saved run to revalidate")
                if ref_file.exists():
                    run_id = ref_file.read_text().strip()
                else:
                    requirements = ProjectRequirements(
                        project_id=lock.project_id,
                        schema_version="0.1.0",
                        content_version="1",
                        scope_site_ids=(self.materials.museum.environment_id,),
                        languages=("en", "zh"),
                        target_story_minutes=None,
                        theme_brief=self.brief,
                        accessibility_requirements=(
                            "Linked source reading at registered observation stations",
                        ),
                        distribution_scope="internal_preview",
                    )
                    await post(
                        "/api/v1/projects",
                        CreateProject(
                            name="Private Story automation",
                            provider="local_manifest",
                            folder_id="story-inputs",
                            requirements=requirements,
                        ),
                    )
                    policy_ref = ArtifactRef.model_validate_json(
                        (await get(f"/api/v1/projects/{lock.project_id}/policy")).content
                    )
                    response = await post(
                        f"/api/v1/projects/{lock.project_id}/runs",
                        CreateRun(
                            policy_ref=policy_ref,
                            budget_policy=BudgetPolicy(
                                max_model_requests=1,
                                max_input_tokens=600000,
                                max_output_tokens=16000,
                                max_search_requests=0,
                                max_fetch_requests=0,
                                max_active_seconds=300,
                                max_cost_microusd=1,
                            ),
                        ),
                    )
                    run_id = RunRecord.model_validate_json(response.content).state.run_id
                    ref_file.write_text(run_id, encoding="utf-8")
                for _ in range(1200):
                    record = RunRecord.model_validate_json(
                        (await get(f"/api/v1/runs/{run_id}")).content
                    )
                    self.save("run-result.json", record)
                    artifact = next(
                        (
                            a
                            for a in reversed(record.artifacts)
                            if a.reference.artifact_id.endswith(":draft")
                        ),
                        None,
                    )
                    if artifact:
                        draft = NarrativeDraft.model_validate_json(artifact.payload_json)
                        self.save("narrative-draft.json", draft)
                        check = StoryDraftInspector().inspect(
                            draft,
                            self.materials.museum,
                            frozenset(c.claim_id for c in self.materials.index.candidate_claims),
                            frozenset(s.source_id for s in self.materials.index.sources),
                            require_spatial_intents=True,
                            expected_catalog_sha256=load_gameplay_catalog().sha256,
                            capabilities=load_gameplay_catalog(),
                        )
                        self.save("story-check.json", check)
                        (self.output / "story.md").write_text(
                            StoryDraftInspector().readable(draft), encoding="utf-8"
                        )
                        for name in ("budget", "executions"):
                            (self.output / (name + ".json")).write_bytes(
                                (await get(f"/api/v1/runs/{run_id}/{name}")).content
                            )
                        self.export_receipts(run_id)
                        if check.status != "ready":
                            raise ServiceError(
                                "STORY_DRAFT_INVALID", "Inspect the saved task/source check report"
                            )
                        return self.output / "story.md"
                    state = record.state
                    base = f"/api/v1/runs/{run_id}"
                    if state.node == "select_candidate" and state.status == "needs_review":
                        if not record.control.internal_preview_continuation:
                            await post(
                                base + "/internal-preview-continuation",
                                RunCommand(
                                    expected_revision=state.revision,
                                    reason=(
                                        "Owner authorized unattended private Story authoring; "
                                        "no public "
                                        "approval"
                                    ),
                                ),
                            )
                        else:
                            item = next(
                                a
                                for a in reversed(record.artifacts)
                                if a.reference.kind == "candidate_set"
                            )
                            candidate = CandidateSetDraft.model_validate_json(
                                item.payload_json
                            ).candidates[0]
                            await post(
                                base + "/candidate-selections",
                                SelectCandidate(
                                    expected_revision=state.revision,
                                    candidate_set_hash=item.reference.sha256,
                                    candidate_id=candidate.candidate_id,
                                    reason=(
                                        "Host-selected input scope; not a model-discovered "
                                        "or human-rated "
                                        "plot"
                                    ),
                                ),
                            )
                    elif state.node == "evidence_review" and state.status == "waiting_review":
                        review = next(
                            r
                            for r in record.review_requests
                            if r.request_id == state.pending_review_id
                        )
                        await post(
                            base + "/review-decisions",
                            SubmitReview(
                                expected_revision=state.revision,
                                request_id=review.request_id,
                                decisions=tuple(
                                    ReviewChoice(
                                        target_id=t.target_id,
                                        target_version=t.version,
                                        target_hash=t.sha256,
                                        decision="approved",
                                        reason=(
                                            "Automated private continuation only; "
                                            "uncertainty retained, no "
                                            "human or public acceptance"
                                        ),
                                    )
                                    for t in review.targets
                                ),
                            ),
                        )
                    elif (
                        self.revalidate_saved_response
                        and not revalidation_started
                        and state.status == "failed"
                        and state.last_error is not None
                        and state.last_error.code == "MODEL_OUTPUT_INVALID"
                    ):
                        revalidation_started = True
                        await post(
                            base + "/resume",
                            RunCommand(
                                expected_revision=state.revision,
                                reason=(
                                    "Local cached-response revalidation; provider calls disabled"
                                ),
                            ),
                        )
                    elif (
                        state.status == "needs_review" and state.last_error is not None
                    ) or state.status in {
                        "blocked",
                        "failed",
                        "needs_changes",
                        "budget_exhausted",
                        "no_feasible_story",
                        "cancelled",
                    }:
                        for name in ("budget", "executions"):
                            (self.output / (name + ".json")).write_bytes(
                                (await get(base + "/" + name)).content
                            )
                        self.export_receipts(run_id)
                        raise ServiceError(
                            "STORY_AUTOMATION_STOPPED",
                            "Run stopped; inspect saved receipts before any retry",
                        )
                    await asyncio.sleep(0.25)
                raise ServiceError(
                    "STORY_WAIT_EXPIRED",
                    "Saved run remains authoritative; do not resend model calls",
                )
