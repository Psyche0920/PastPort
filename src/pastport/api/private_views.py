"""Private content routes; all bytes resolve through server-selected package/source identities."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from pastport.api.transport import read_body
from pastport.application.change_impact import ChangeImpactService, CompareChanges
from pastport.application.models import Actor, ServiceError
from pastport.application.preview_service import PreviewService
from pastport.application.previews import CreatePreview, PrivatePackageView, SessionView
from pastport.application.source_views import SourceViews
from pastport.domain.common import Identifier, Sha256
from pastport.domain.game import ActionRequest
from pastport.domain.resources import ResourceReference
from pastport.workflow.stages import StageRunner

# Private bytes are never cached as public assets or interpreted as active source documents.
PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'",
}


class PrivateViewRoutes:
    def __init__(
        self,
        previews: PreviewService,
        sources: SourceViews,
        stages: StageRunner,
        authenticate: Callable[[Request], Actor],
    ) -> None:
        self.previews = previews
        self.sources = sources
        self.stages = stages
        self.authenticate = authenticate

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/api/v1/session")
        async def session(request: Request) -> JSONResponse:
            actor = self.authenticate(request)
            return JSONResponse(
                SessionView(
                    actor_id=actor.actor_id,
                    roles=actor.roles,
                    project_ids=actor.project_ids,
                    environment=self.stages.environment,
                ).model_dump(mode="json"),
                headers={"Cache-Control": "no-store"},
            )

        @router.post("/api/v1/runs/{run_id}/previews")
        async def create_preview(run_id: str, request: Request) -> JSONResponse:
            actor = self.authenticate(request)
            self.previews.run(run_id, actor)
            payload = await read_body(request, CreatePreview)
            key = request.headers.get("Idempotency-Key", "")
            # Editorial request keys are opaque, not game identities; keep their existing bounds.
            if not key or len(key) > 160:
                raise ServiceError(
                    "IDEMPOTENCY_KEY_REQUIRED", "Supply a bounded Idempotency-Key header", 422
                )
            result = await asyncio.to_thread(self.previews.create, actor, run_id, payload, key)
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.get("/api/v1/runs/{run_id}/previews/{preview_id}")
        async def preview(run_id: str, preview_id: str, request: Request) -> JSONResponse:
            result = await asyncio.to_thread(
                self.previews.get, self.authenticate(request), run_id, preview_id
            )
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.post("/api/v1/runs/{run_id}/previews/{preview_id}/actions")
        async def action(run_id: str, preview_id: str, request: Request) -> JSONResponse:
            actor = self.authenticate(request)
            self.previews.run(run_id, actor)
            payload = await read_body(request, ActionRequest)
            result = await asyncio.to_thread(
                self.previews.apply, actor, run_id, preview_id, payload
            )
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.get("/api/v1/runs/{run_id}/previews/{preview_id}/assets/{asset_id}")
        async def asset(run_id: str, preview_id: str, asset_id: str, request: Request) -> Response:
            result = await asyncio.to_thread(
                self.previews.asset, self.authenticate(request), run_id, preview_id, asset_id
            )
            return Response(result.content, media_type=result.media_type, headers=PRIVATE_HEADERS)

        @router.get("/api/v1/runs/{run_id}/sources/{source_id}")
        async def document(
            run_id: str,
            source_id: str,
            request: Request,
            source_version: Annotated[Identifier, Query()],
            file_sha256: Annotated[Sha256, Query()],
        ) -> JSONResponse:
            run = self.previews.editorial.run(run_id, self.authenticate(request))
            source = self.sources.source(run, source_id, source_version, file_sha256)
            result = await asyncio.to_thread(self.sources.document, run, source)
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.get("/api/v1/runs/{run_id}/sources/{source_id}/content")
        async def source_content(
            run_id: str,
            source_id: str,
            request: Request,
            source_version: Annotated[Identifier, Query()],
            file_sha256: Annotated[Sha256, Query()],
        ) -> Response:
            run = self.previews.editorial.run(run_id, self.authenticate(request))
            source = self.sources.source(run, source_id, source_version, file_sha256)
            result = await asyncio.to_thread(self.sources.content, run, source)
            return Response(
                result.content,
                media_type="application/octet-stream",
                headers={**PRIVATE_HEADERS, "Content-Disposition": "attachment"},
            )

        def release(project_id: str, release_id: str, actor: Actor) -> PrivatePackageView:
            self.previews.editorial.project(project_id, actor)
            current = self.stages.current_release(project_id)
            if current is None or current.manifest.release_id != release_id:
                raise ServiceError(
                    "RELEASE_UNAVAILABLE",
                    "Requested private release is no longer current and valid",
                    404,
                )
            package = self.stages.package_loader.load(
                self.stages.releases / project_id / release_id / "package.json",
                current.manifest.runtime_ref,
            )
            return PrivatePackageView(
                runtime_ref=current.manifest.runtime_ref, runtime_package=package
            )

        @router.get("/api/v1/projects/{project_id}/releases/{release_id}/package")
        async def release_package(
            project_id: str, release_id: str, request: Request
        ) -> JSONResponse:
            result = await asyncio.to_thread(
                release, project_id, release_id, self.authenticate(request)
            )
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.get("/api/v1/projects/{project_id}/releases/{release_id}/assets/{asset_id}")
        async def release_asset(
            project_id: str, release_id: str, asset_id: str, request: Request
        ) -> Response:
            result = await asyncio.to_thread(
                release, project_id, release_id, self.authenticate(request)
            )
            entry = next(
                (
                    item
                    for item in result.runtime_package.media_manifest
                    if item.asset_id == asset_id
                ),
                None,
            )
            if entry is None:
                raise ServiceError("RESOURCE_NOT_REGISTERED", "Asset is not in this release", 404)
            resource = await asyncio.to_thread(
                self.previews.resources().read,
                ResourceReference(
                    project_id=project_id, resource_id=asset_id, kind="asset", sha256=entry.sha256
                ),
                20 * 1024 * 1024,
            )
            return Response(
                resource.content, media_type=resource.media_type, headers=PRIVATE_HEADERS
            )

        @router.post("/api/v1/runs/{run_id}/change-impact")
        async def change_impact(run_id: str, request: Request) -> JSONResponse:
            actor = self.authenticate(request)
            self.previews.editorial.run(run_id, actor)
            payload = await read_body(request, CompareChanges)
            result = await asyncio.to_thread(
                ChangeImpactService(self.previews.editorial, self.stages).compare,
                actor,
                run_id,
                payload,
            )
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        return router


def static_router() -> APIRouter:
    router = APIRouter()
    player = Path(__file__).resolve().parents[1] / "player"
    player_modules = frozenset(
        {
            "actions.mjs",
            "context.mjs",
            "errors.mjs",
            "generated-schemas.mjs",
            "preparation.mjs",
            "rules.mjs",
            "runtime.mjs",
            "validation.mjs",
        }
    )
    workbench_modules = frozenset(
        {"api-client.mjs", "workbench.mjs", "player-view.mjs", "views.mjs", "workbench.css"}
    )

    @router.get("/static/{group}/{module_name}")
    async def module(group: str, module_name: str) -> Response:
        if group == "player" and module_name in player_modules:
            path = player / module_name
        elif group == "workbench" and module_name in workbench_modules:
            path = Path(__file__).with_name(module_name)
        else:
            raise ServiceError("STATIC_NOT_FOUND", "Trusted module is not registered", 404)
        # Only trusted deployment files are exposed, never source content.
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ServiceError(
                "STATIC_UNAVAILABLE", "Trusted module is unavailable", 503
            ) from error
        return Response(
            content,
            media_type="text/css" if module_name.endswith(".css") else "text/javascript",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"},
        )

    return router
