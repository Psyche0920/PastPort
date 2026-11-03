"""Local authenticated editorial API with strict JSON transport and a durable background worker."""

import asyncio
import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from pastport.adapters.assembly import PackageAssembler
from pastport.adapters.content import LocalContentFiles, LocalEvidenceAdapter, LocalNarrativeAdapter
from pastport.adapters.database import EditorialDatabase
from pastport.adapters.organizer_store import OrganizerStore
from pastport.adapters.package_files import LocalPackageFileReader
from pastport.adapters.player_process import NodePlayerProcess, PlayerComponentError
from pastport.adapters.player_saves import SQLitePlayerSaves
from pastport.adapters.previews import SQLitePreviews
from pastport.adapters.resources import LocalResourceReader
from pastport.adapters.story_3d import Story3DAssemblyAdapter
from pastport.api.organizer import OrganizerRoutes
from pastport.api.organizer_accounts import OrganizerAccounts
from pastport.api.private_views import PrivateViewRoutes, static_router
from pastport.api.request_logging import RequestLoggingMiddleware
from pastport.api.settings import AppSettings
from pastport.api.transport import read_body
from pastport.application.execution_models import ProviderRegistration
from pastport.application.execution_runtime import ExecutionRuntime
from pastport.application.models import (
    Actor,
    CreateProject,
    CreateRun,
    RequestReceipt,
    RunCommand,
    SelectCandidate,
    ServiceError,
    SetLocks,
    SubmitReview,
    SubmitRevision,
)
from pastport.application.module_selection import select_module
from pastport.application.operational_service import OperationalService
from pastport.application.operations import AmendBudget, ReconcileUsage, ResubmitReview
from pastport.application.organizer import OrganizerService
from pastport.ports.story_reuse import StoryReusePort
from pastport.application.package_loader import RuntimePackageLoader
from pastport.application.player_preparation import PlayerInitialStateResponse
from pastport.application.player_runtime import (
    PlayerRuntimeError,
    PlayerRuntimeProcess,
    SharedPlayerRuntime,
)
from pastport.application.player_service import PlayerService
from pastport.application.preview_service import PreviewService
from pastport.application.reliability import ReviewAuthority, RevokeReview
from pastport.application.service import EditorialService
from pastport.application.source_views import SourceViews
from pastport.application.workflow_control import RequestNarrativeAction
from pastport.domain.capabilities import initial_capabilities
from pastport.domain.common import CanonicalSerializer, Contract
from pastport.domain.game import ActionRequest
from pastport.domain.organizer import OrganizerCatalog
from pastport.domain.package_loading import PackageLoadError
from pastport.domain.player_saves import (
    CreatePlayerSave,
    PlayerSaveKey,
    PlayerSaveView,
    SavedActionResult,
)
from pastport.ports.execution import ModuleServices
from pastport.ports.modules import AssemblyPort, EvidencePort, NarrativePort, PackageValidatorPort
from pastport.ports.organizer import OrganizerProduction
from pastport.ports.organizer_review import OrganizerReviewGateway
from pastport.ports.organizer_inputs import OrganizerInputPreparer
from pastport.ports.resources import ResourceReader
from pastport.ports.source_text import SourceTextExtractor
from pastport.ports.story_inputs import MatchedEnvironmentReader
from pastport.workflow.stages import StageRunner
from pastport.workflow.worker import EditorialWorker


def create_app(
    settings: AppSettings,
    *,
    organizer_production: OrganizerProduction | None = None,
    organizer_inputs: OrganizerInputPreparer | None = None,
    organizer_reviews: OrganizerReviewGateway | None = None,
    organizer_story_reuse: StoryReusePort | None = None,
    evidence: EvidencePort | None = None,
    narrative: NarrativePort | None = None,
    assembly: AssemblyPort | None = None,
    validator: PackageValidatorPort | None = None,
    resources: ResourceReader | None = None,
    source_text_extractor: SourceTextExtractor | None = None,
    environment_reader: MatchedEnvironmentReader | None = None,
    providers: tuple[ProviderRegistration, ...] = (),
    player_process: PlayerRuntimeProcess | None = None,
    evidence_factory: Callable[[ModuleServices], EvidencePort] | None = None,
    narrative_factory: Callable[[ModuleServices], NarrativePort] | None = None,
) -> FastAPI:
    directory = settings.data_directory.resolve()
    database = EditorialDatabase(directory / "editorial.sqlite3")
    authority = ReviewAuthority(
        tuple(account.actor for account in settings.accounts), settings.environment
    )
    content_directory = settings.fixture_directory or settings.content_directory
    content = (
        LocalContentFiles(content_directory, allow_synthetic=settings.environment == "test")
        if content_directory
        else None
    )
    resource_directory = settings.resource_directory or content_directory
    resource_reader, resource_mode = select_module(
        "resources",
        settings.resources_mode,
        resources,
        (
            lambda: LocalResourceReader(
                resource_directory, fixture_projects=settings.environment == "test"
            )
        )
        if resource_directory is not None
        else None,
    )
    execution = ExecutionRuntime(
        database,
        settings.execution,
        settings.skill_directory or Path(__file__).resolve().parents[3] / "skills",
        providers,
        resource_reader,
        authority,
        settings.environment,
        source_text_extractor=source_text_extractor,
        environment_reader=environment_reader,
    )
    service = EditorialService(
        database, settings.environment, authority, execution.policy, execution.guard.binding
    )
    if evidence_factory is not None:
        if evidence is not None:
            raise ValueError("Choose an evidence adapter or factory")
        evidence = evidence_factory(execution.services)
    if narrative_factory is not None:
        if narrative is not None:
            raise ValueError("Choose a narrative adapter or factory")
        narrative = narrative_factory(execution.services)
    evidence_adapter, evidence_mode = select_module(
        "evidence",
        settings.evidence_mode,
        evidence,
        (lambda: LocalEvidenceAdapter(content, resource_reader)) if content is not None else None,
    )
    narrative_adapter, narrative_mode = select_module(
        "narrative",
        settings.narrative_mode,
        narrative,
        (lambda: LocalNarrativeAdapter(content)) if content is not None else None,
    )
    assembler = PackageAssembler(resource_reader) if resource_reader is not None else None
    assembly_adapter = assembly if assembly is not None else assembler
    if settings.story_3d_preparation_directory is not None:
        if assembly_adapter is None:
            raise ValueError("Story 3D delivery requires the shared assembly adapter")
        assert settings.story_3d_museum_directory is not None
        assert settings.story_3d_output_directory is not None
        assembly_adapter = Story3DAssemblyAdapter(
            assembly_adapter,
            settings.story_3d_preparation_directory,
            settings.story_3d_museum_directory,
            settings.story_3d_output_directory,
        )
    stages = StageRunner(
        database,
        directory / "releases",
        resource_reader,
        evidence_adapter,
        narrative_adapter,
        assembly_adapter,
        validator if validator is not None else assembler,
        initial_capabilities(),
        settings.environment,
        authority,
        RuntimePackageLoader(initial_capabilities(), LocalPackageFileReader()),
        execution,
        authoring_constraints=settings.story_host_constraints,
        authoring_structure=settings.story_structure,
    )
    player_repository = SQLitePlayerSaves(directory / "player.sqlite3")
    operations = OperationalService(database, authority, stages.review_targets)
    worker = EditorialWorker(stages, directory / "checkpoints.sqlite3")

    if organizer_production is None:
        from pastport.adapters.organizer_production import SDKOrganizerProduction
        from pastport.adapters.organizer_review import SDKOrganizerReview

        organizer_production = SDKOrganizerProduction()
        if organizer_story_reuse is None:
            from pastport.adapters.story_reuse import StoryReuseAdapter
            organizer_story_reuse = StoryReuseAdapter()
        if organizer_reviews is None:
            organizer_reviews = SDKOrganizerReview()
    organizer_catalog = (
        OrganizerCatalog.model_validate_json(settings.organizer_catalog.read_bytes())
        if settings.organizer_catalog is not None
        else OrganizerCatalog()
    )
    if organizer_inputs is None:
        from pastport.adapters.organizer_native import SDKUploadedInputPreparer

        organizer_inputs = SDKUploadedInputPreparer()
    organizer_store = OrganizerStore(directory / "organizer")
    organizer = OrganizerService(
        organizer_store,
        organizer_catalog,
        organizer_production,
        input_preparer=organizer_inputs,
        player_assets=settings.organizer_player_assets,
        reviews=organizer_reviews,
        story_reuse=organizer_story_reuse,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(asyncio.to_thread(worker.run))
        await asyncio.to_thread(worker.ready.wait, 10)
        if not worker.ready.is_set() or worker.failure is not None:
            worker.stop()
            await task
            raise ServiceError("WORKER_START_FAILED", "Worker could not start", 503)
        try:
            with organizer_store.ownership():
                organizer.startup()
                try:
                    yield
                finally:
                    await organizer.close()
                    await organizer_routes.previews.close()
                    if organizer_routes.mounted_previews is not None:
                        await organizer_routes.mounted_previews.close()
        finally:
            worker.stop()
            await task

    app = FastAPI(
        title="PastPort editorial service",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(RequestLoggingMiddleware, environment=settings.environment)

    organizer_accounts = OrganizerAccounts(
        settings.accounts,
        settings.accounts_file,
        allow_local_setup=settings.organizer_local_admin_setup,
    )

    def authenticate(request: Request) -> Actor:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ServiceError("AUTHENTICATION_REQUIRED", "Bearer authentication is required", 401)
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        for account in organizer_accounts.credentials():
            if account.token_sha256 is not None and hmac.compare_digest(
                digest, account.token_sha256
            ):
                return account.actor
        raise ServiceError("AUTHENTICATION_INVALID", "Authentication failed", 401)

    organizer_routes = OrganizerRoutes(organizer, authenticate, organizer_accounts)
    app.include_router(organizer_routes.router())

    def receipt(
        request: Request, actor: Actor, payload: Contract, status_code: int
    ) -> RequestReceipt:
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 160:
            raise ServiceError(
                "IDEMPOTENCY_KEY_REQUIRED", "Supply a bounded Idempotency-Key header", 422
            )
        return RequestReceipt(
            scope=actor.actor_id + ":" + request.method + ":" + request.url.path,
            request_key=key,
            payload_hash=CanonicalSerializer.digest(payload),
            response_json="",
            status_code=status_code,
        )

    def mutate(receipt: RequestReceipt, perform: Callable[[], Contract]) -> JSONResponse:
        previous = database.receipt(receipt.scope, receipt.request_key, receipt.payload_hash)
        if previous is not None:
            return JSONResponse(
                json.loads(previous.response_json), status_code=previous.status_code
            )
        try:
            result = perform()
        except ServiceError:
            previous = database.receipt(receipt.scope, receipt.request_key, receipt.payload_hash)
            if previous is not None:
                return JSONResponse(
                    json.loads(previous.response_json), status_code=previous.status_code
                )
            raise
        return JSONResponse(result.model_dump(mode="json"), status_code=receipt.status_code)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError) -> JSONResponse:
        request.scope["pastport.error_code"] = error.code
        return JSONResponse(
            {
                "code": error.code,
                "message": str(error),
                "retryable": error.status_code >= 500,
                "owner": "workflow",
                "field_path": "",
                "safe_details": {},
                "run_id": request.path_params.get("run_id"),
            },
            status_code=error.status_code,
        )

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, error: ValidationError) -> JSONResponse:
        request.scope["pastport.error_code"] = "INPUT_INVALID"
        fields = [
            ".".join(str(part) for part in item["loc"])
            for item in error.errors(include_input=False)
        ]
        return JSONResponse(
            {
                "code": "INPUT_INVALID",
                "message": (
                    "项目编号不能含空格或中文，请使用英文字母、数字及 - _ . :，例如 3d-test。"
                    if request.url.path == "/organizer/api/materials"
                    and "project_id" in fields
                    else "证据模型调用上限须为1至100的整数。"
                    if request.url.path.startswith("/organizer/api/")
                    and any(field.split(".")[-1] == "max_evidence_calls" for field in fields)
                    else "环境匹配模型调用上限须为1至40的整数。"
                    if request.url.path.startswith("/organizer/api/")
                    and any(field.split(".")[-1] == "max_environment_calls" for field in fields)
                    else "Request does not match the contract"
                ),
                "retryable": False,
                "owner": "workflow",
                "field_path": fields[0] if fields else "",
                "safe_details": {"fields": fields},
                "run_id": request.path_params.get("run_id"),
            },
            status_code=422,
        )

    @app.get("/", response_class=HTMLResponse)
    async def workbench() -> str:
        return Path(__file__).with_name("workbench.html").read_text(encoding="utf-8")

    @app.get("/api/v1/health")
    async def health() -> JSONResponse:
        healthy = worker.ready.is_set() and worker.failure is None
        return JSONResponse(
            {
                "status": "ready" if healthy else "unavailable",
                "environment": settings.environment,
                "modules": {
                    "evidence": evidence_mode,
                    "narrative": narrative_mode,
                    "resources": resource_mode,
                },
            },
            status_code=200 if healthy else 503,
        )

    @app.get("/api/v1/projects")
    async def projects(request: Request) -> JSONResponse:
        actor = authenticate(request)
        allowed = [
            project.model_dump(mode="json")
            for project in database.projects()
            if actor.project_ids is None or project.project_id in actor.project_ids
        ]
        return JSONResponse(allowed)

    @app.post("/api/v1/projects")
    async def create_project(request: Request) -> JSONResponse:
        actor = authenticate(request)
        payload = await read_body(request, CreateProject)
        service.authorize(actor, payload.requirements.project_id, "editor")
        entry = receipt(request, actor, payload, 201)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.create_project(payload, actor, entry)
        )

    @app.get("/api/v1/projects/{project_id}")
    async def project(project_id: str, request: Request) -> JSONResponse:
        return JSONResponse(
            service.project(project_id, authenticate(request)).model_dump(mode="json")
        )

    @app.get("/api/v1/projects/{project_id}/policy")
    async def policy(project_id: str, request: Request) -> JSONResponse:
        service.project(project_id, authenticate(request))
        return JSONResponse(service.policy_reference(project_id).model_dump(mode="json"))

    @app.get("/api/v1/projects/{project_id}/release")
    async def current_release(project_id: str, request: Request) -> JSONResponse:
        service.project(project_id, authenticate(request))
        release = await asyncio.to_thread(stages.current_release, project_id)
        if release is None:
            raise ServiceError(
                "RELEASE_UNAVAILABLE", "Project has no currently valid private release", 404
            )
        return JSONResponse(release.model_dump(mode="json"))

    @app.exception_handler(PlayerRuntimeError)
    @app.exception_handler(PlayerComponentError)
    @app.exception_handler(PackageLoadError)
    async def player_error(
        request: Request, error: PlayerRuntimeError | PlayerComponentError | PackageLoadError
    ) -> JSONResponse:
        code = error.code
        request.scope["pastport.error_code"] = code
        status = 404 if code == "SAVE_NOT_FOUND" else 409
        if code.endswith("TOO_LARGE"):
            status = 413
        elif code in {
            "SAVE_STORAGE_FAILED",
            "PLAYER_NODE_UNAVAILABLE",
            "PLAYER_PROCESS_UNAVAILABLE",
            "PLAYER_TIMEOUT",
            "PLAYER_RESPONSE_INVALID",
            "PLAYER_PROCESS_FAILED",
            "PLAYER_COMPONENT_FAILED",
            "RUNTIME_PACKAGE_UNREADABLE",
        }:
            status = 503
        return JSONResponse(
            {"code": code, "message": str(error), "owner": "runtime", "retryable": status == 503},
            status_code=status,
        )

    def player_service(project_id: str) -> tuple[PlayerService, SharedPlayerRuntime]:
        release = stages.current_release(project_id)
        if release is None:
            raise ServiceError(
                "RELEASE_UNAVAILABLE", "Project has no currently valid private release", 404
            )
        content = LocalPackageFileReader().read(
            stages.releases / project_id / release.manifest.release_id / "package.json",
            stages.package_loader.maximum_bytes,
        )
        runtime = SharedPlayerRuntime(
            content,
            release.manifest.runtime_ref,
            release.manifest.release_id,
            stages.package_loader,
            player_process if player_process is not None else NodePlayerProcess(),
        )
        return PlayerService(
            player_repository, runtime, runtime.package, runtime.release_id
        ), runtime

    def player_key(project_id: str, save_id: str, request: Request) -> PlayerSaveKey:
        actor = authenticate(request)
        service.project(project_id, actor)
        return PlayerSaveKey(
            environment=settings.environment,
            actor_id=actor.actor_id,
            project_id=project_id,
            save_id=save_id,
        )

    @app.get("/api/v1/projects/{project_id}/player-initial-state")
    async def player_initial_state(project_id: str, request: Request) -> JSONResponse:
        service.project(project_id, authenticate(request))

        def initialize() -> JSONResponse:
            _, runtime = player_service(project_id)
            state = runtime.initial_state(runtime.package, runtime.release_id)
            return JSONResponse(PlayerInitialStateResponse(state=state).model_dump(mode="json"))

        return await asyncio.to_thread(initialize)

    @app.post("/api/v1/projects/{project_id}/player-saves")
    async def create_player_save(project_id: str, request: Request) -> JSONResponse:
        # Authenticate before parsing caller-controlled payloads.
        service.project(project_id, authenticate(request))
        payload = await read_body(request, CreatePlayerSave)
        key = player_key(project_id, payload.save_id, request)

        def create() -> JSONResponse:
            player, _ = player_service(project_id)
            state = player.create(key)
            return JSONResponse(
                PlayerSaveView(save_id=key.save_id, persisted=True, state=state).model_dump(
                    mode="json"
                )
            )

        return await asyncio.to_thread(create)

    @app.get("/api/v1/projects/{project_id}/player-saves/{save_id}")
    async def get_player_save(project_id: str, save_id: str, request: Request) -> JSONResponse:
        key = player_key(project_id, save_id, request)

        def load() -> JSONResponse:
            player, _ = player_service(project_id)
            return JSONResponse(
                PlayerSaveView(
                    save_id=key.save_id, persisted=True, state=player.load(key)
                ).model_dump(mode="json")
            )

        return await asyncio.to_thread(load)

    @app.post("/api/v1/projects/{project_id}/player-saves/{save_id}/actions")
    async def player_action(project_id: str, save_id: str, request: Request) -> JSONResponse:
        key = player_key(project_id, save_id, request)
        action = await read_body(request, ActionRequest)

        def apply() -> JSONResponse:
            player, _ = player_service(project_id)
            result = player.apply(key, action)
            return JSONResponse(
                SavedActionResult(save_id=save_id, persisted=True, result=result).model_dump(
                    mode="json"
                )
            )

        return await asyncio.to_thread(apply)

    @app.post("/api/v1/projects/{project_id}/runs")
    async def create_run(project_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        service.project(project_id, actor)
        service.authorize(actor, project_id, "editor")
        payload = await read_body(request, CreateRun)
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.create_run(project_id, payload, actor, entry)
        )

    @app.get("/api/v1/runs/{run_id}")
    async def run(run_id: str, request: Request) -> JSONResponse:
        return JSONResponse(service.run(run_id, authenticate(request)).model_dump(mode="json"))

    @app.get("/api/v1/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: int = 0) -> JSONResponse:
        service.run(run_id, authenticate(request))
        if after < 0:
            raise ServiceError("CURSOR_INVALID", "Event cursor must be nonnegative", 422)
        return JSONResponse(
            [event.model_dump(mode="json") for event in database.events(run_id, after)]
        )

    @app.get("/api/v1/runs/{run_id}/reviews")
    async def reviews(run_id: str, request: Request) -> JSONResponse:
        record = service.run(run_id, authenticate(request))
        return JSONResponse(
            {
                "pending_review_id": record.state.pending_review_id,
                "requests": [item.model_dump(mode="json") for item in record.review_requests],
                "revoked_decision_ids": list(database.revoked_reviews(run_id)),
                "decisions": [item.model_dump(mode="json") for item in record.review_decisions],
            }
        )

    @app.post("/api/v1/runs/{run_id}/candidate-selections")
    async def select_candidate(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "narrative")
        payload = await read_body(request, SelectCandidate)
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.select_candidate(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/review-decisions")
    async def submit_review(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        payload = await read_body(request, SubmitReview)
        pending = next(
            (item for item in record.review_requests if item.request_id == payload.request_id), None
        )
        if pending is not None:
            service.authorize(
                actor,
                record.state.project_id,
                "publisher" if pending.gate == "publication" else pending.gate,
            )
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.submit_review(run_id, payload, actor, entry)
        )

    @app.get("/api/v1/runs/{run_id}/budget")
    async def budget(run_id: str, request: Request) -> JSONResponse:
        service.run(run_id, authenticate(request))
        result = await asyncio.to_thread(database.budget, run_id)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/api/v1/runs/{run_id}/review-revocations")
    async def revoke_review(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        payload = await read_body(request, RevokeReview)
        decision = next(
            (item for item in database.reviews(run_id) if item.decision_id == payload.decision_id),
            None,
        )
        if decision is None:
            raise ServiceError("REVIEW_STALE", "Review does not exist")
        authority.actor(
            actor.actor_id,
            record.state.project_id,
            "publisher" if decision.gate == "publication" else decision.gate,
        )
        entry = receipt(request, actor, payload, 200)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.revoke_review(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "editor")
        payload = await read_body(request, RunCommand)
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.cancel(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/internal-preview-continuation")
    async def internal_preview_continuation(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "operator")
        payload = await read_body(request, RunCommand)
        entry = receipt(request, actor, payload, 200)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.enable_internal_preview(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/resume")
    async def resume(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "editor")
        payload = await read_body(request, RunCommand)
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.resume(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/narrative-requests")
    async def narrative_action(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "narrative")
        payload = await read_body(request, RequestNarrativeAction)
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.request_narrative_action(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/revisions")
    async def revise(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "narrative")
        payload = await read_body(request, SubmitRevision)
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.revise(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/locks")
    async def locks(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        record = service.run(run_id, actor)
        service.authorize(actor, record.state.project_id, "narrative")
        payload = await read_body(request, SetLocks)
        entry = receipt(request, actor, payload, 200)
        return await asyncio.to_thread(
            mutate, entry, lambda: service.set_locks(run_id, payload, actor, entry)
        )

    @app.get("/api/v1/runs/{run_id}/interventions")
    async def interventions(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        return JSONResponse(
            (await asyncio.to_thread(operations.inspect, run_id, actor)).model_dump(mode="json")
        )

    @app.post("/api/v1/runs/{run_id}/usage-reconciliations")
    async def reconcile_usage(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        operations.authorized(run_id, actor, "operator")
        payload = await read_body(request, ReconcileUsage)
        entry = receipt(request, actor, payload, 200)
        return await asyncio.to_thread(
            mutate, entry, lambda: operations.reconcile(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/budget-amendments")
    async def amend_budget(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        operations.authorized(run_id, actor, "operator")
        payload = await read_body(request, AmendBudget)
        entry = receipt(request, actor, payload, 200)
        return await asyncio.to_thread(
            mutate, entry, lambda: operations.amend(run_id, payload, actor, entry)
        )

    @app.post("/api/v1/runs/{run_id}/review-resubmissions")
    async def resubmit_review(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(request)
        service.run(run_id, actor)
        payload = await read_body(request, ResubmitReview)
        decision = next(
            (d for d in database.reviews(run_id) if d.decision_id == payload.decision_id), None
        )
        if decision is None:
            raise ServiceError("REVIEW_STALE", "Review decision does not exist")
        operations.authorized(
            run_id, actor, "publisher" if decision.gate == "publication" else decision.gate
        )
        entry = receipt(request, actor, payload, 202)
        return await asyncio.to_thread(
            mutate, entry, lambda: operations.resubmit(run_id, payload, actor, entry)
        )

    @app.get("/api/v1/runs/{run_id}/executions")
    async def executions(run_id: str, request: Request) -> JSONResponse:
        service.run(run_id, authenticate(request))
        return JSONResponse(
            [item.model_dump(mode="json") for item in database.execution_summaries(run_id)]
        )

    @app.get("/api/v1/runs/{run_id}/artifacts")
    async def artifacts(run_id: str, request: Request) -> JSONResponse:
        record = service.run(run_id, authenticate(request))
        return JSONResponse([item.reference.model_dump(mode="json") for item in record.artifacts])

    @app.get("/api/v1/artifacts/{artifact_id}")
    async def artifact(
        artifact_id: str, request: Request, content_version: str | None = None
    ) -> JSONResponse:
        actor = authenticate(request)
        run_id = artifact_id.partition(":")[0]
        record = service.run(run_id, actor)
        item = next(
            (
                item
                for item in reversed(record.artifacts)
                if item.reference.artifact_id == artifact_id
                and (content_version is None or item.reference.content_version == content_version)
            ),
            None,
        )
        if item is None:
            receipt_record = database.execution_receipt(artifact_id)
            if receipt_record is not None and receipt_record.artifact is not None:
                candidate = receipt_record.artifact
                if (
                    candidate.reference.project_id == record.state.project_id
                    and candidate.reference.artifact_id == artifact_id
                    and (
                        content_version is None
                        or candidate.reference.content_version == content_version
                    )
                ):
                    item = candidate
        if item is None:
            raise ServiceError("ARTIFACT_NOT_FOUND", "Artifact does not exist", 404)
        return JSONResponse(
            {
                "reference": item.reference.model_dump(mode="json"),
                "payload": json.loads(item.payload_json),
            }
        )

    @app.get("/api/v1/public/projects/{project_id}/release")
    async def public_release(project_id: str) -> JSONResponse:
        raise ServiceError(
            "RELEASE_NOT_PUBLIC", "No production release has passed all publication gates", 404
        )

    previews = PreviewService(
        service,
        stages,
        SQLitePreviews(directory / "previews.sqlite3", settings.environment),
        player_process if player_process is not None else NodePlayerProcess(),
    )
    app.include_router(
        PrivateViewRoutes(
            previews,
            SourceViews(database, stages.resources),
            stages,
            authenticate,
        ).router()
    )
    app.include_router(static_router())
    return app
