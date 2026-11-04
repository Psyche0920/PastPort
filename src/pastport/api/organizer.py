"""Organizer routes share Main accounts; uploaded bytes never choose server paths."""

import asyncio
import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from pastport.adapters.organizer_delivery import MAX_BYTES, delivery_name, import_delivery
from pastport.adapters.organizer_previews import OrganizerPreviewPool
from pastport.adapters.organizer_review_environment import SDKMountedPreviewPool
from pastport.adapters.runtime_resources import runtime_root
from pastport.api.organizer_accounts import OrganizerAccounts
from pastport.api.settings import Credential
from pastport.api.transport import read_body
from pastport.application.models import Actor, ServiceError
from pastport.application.organizer import OrganizerService
from pastport.domain.organizer import (
    OrganizerAdminSetup,
    OrganizerFile,
    OrganizerPasswordLogin,
    OrganizerProjectCreate,
    OrganizerRecovery,
    OrganizerSelection,
    OrganizerStart,
    OrganizerStorageView,
)
from pastport.domain.organizer_inputs import NativePreparedInputs, UploadedProductionStart
from pastport.domain.organizer_review import (
    NativeIntroductionWrite,
    NativeReviewWrite,
    ReviewAcknowledgment,
    ReviewChange,
)
from pastport.domain.story_reuse import StoryReuseConfirmation
from pastport.ports.organizer import MountedEnvironmentPreviews


@dataclass(frozen=True, slots=True)
class _Session:
    actor: Actor
    deadline: float
    account_version: str


class OrganizerRoutes:
    def __init__(
        self,
        service: OrganizerService,
        authenticate: Callable[[Request], Actor],
        accounts: OrganizerAccounts,
    ) -> None:
        self.service, self.authenticate, self.accounts = service, authenticate, accounts
        self.password_slots = asyncio.Semaphore(2)
        self.failed_logins: dict[str, list[float]] = {}
        self.sessions: dict[str, _Session] = {}
        self.previews = OrganizerPreviewPool()
        self.mounted_previews: MountedEnvironmentPreviews | None = None

    def actor(self, request: Request) -> Actor:
        if request.headers.get("authorization"):
            return self.authenticate(request)
        session = self.sessions.get(request.cookies.get("pastport_organizer", ""))
        if session is None or session.deadline < time.monotonic():
            raise ServiceError("AUTHENTICATION_REQUIRED", "请先登录制作后台。", 401)
        account = self.accounts.actor_account(session.actor.actor_id)
        if self.accounts.version(account) != session.account_version:
            raise ServiceError("AUTHENTICATION_REQUIRED", "账户已更新，请重新登录。", 401)
        if request.method not in ("GET", "HEAD") and (
            request.headers.get("x-pastport-edit") != "1"
            or request.headers.get("origin") not in (None, str(request.base_url).rstrip("/"))
        ):
            raise ServiceError("ORGANIZER_ORIGIN_INVALID", "制作请求来源不合法。", 403)
        return account.actor

    def issue_session(self, request: Request, account: Credential) -> JSONResponse:
        actor = account.actor
        self.sessions = {
            key: value for key, value in self.sessions.items() if value.deadline > time.monotonic()
        }
        if len(self.sessions) >= 100:
            raise ServiceError("ORGANIZER_SESSION_LIMIT", "登录会话过多，请稍后再试。", 429)
        key = secrets.token_urlsafe(32)
        self.sessions[key] = _Session(
            actor, time.monotonic() + 8 * 3600, self.accounts.version(account)
        )
        response = JSONResponse(
            {"actor_id": account.actor.actor_id}, headers={"Cache-Control": "no-store"}
        )
        response.set_cookie(
            "pastport_organizer",
            key,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/organizer",
            max_age=8 * 3600,
        )
        return response

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/organizer")

        @router.get("/")
        async def index() -> HTMLResponse:
            root = runtime_root() / "frontend/organizer"
            revision = hashlib.sha256(
                b"".join(
                    (root / name).read_bytes()
                    for name in ("app.mjs", "review.mjs", "i18n.mjs", "app.css")
                )
            ).hexdigest()[:20]
            html = (root / "index.html").read_text()
            html = html.replace('src="assets/app.mjs"', f'src="assets/app.mjs?v={revision}"')
            html = html.replace('href="assets/app.css"', f'href="assets/app.css?v={revision}"')
            return HTMLResponse(
                html,
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": (
                        "default-src 'self'; script-src 'self'; style-src 'self'; con"
                        "nect-src 'self'; img-src 'self' data:; frame-ancestors 'none"
                        "'; object-src 'none'; base-uri 'none'"
                    ),
                },
            )

        @router.get("/assets/{name}")
        async def asset(name: str) -> Response:
            if name not in ("app.mjs", "app.css", "review.mjs", "i18n.mjs"):
                raise ServiceError("ORGANIZER_NOT_FOUND", "找不到此资源。", 404)
            root = runtime_root() / "frontend/organizer"
            headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
            if name in ("app.mjs", "review.mjs"):
                version = hashlib.sha256((root / "review.mjs").read_bytes()).hexdigest()[:20]
                script = (
                    (root / name)
                    .read_text()
                    .replace("from './review.mjs'", f"from './review.mjs?v={version}'")
                )
                language_version = hashlib.sha256((root / "i18n.mjs").read_bytes()).hexdigest()[:20]
                script = script.replace(
                    "from './i18n.mjs'", f"from './i18n.mjs?v={language_version}'"
                )
                return Response(script, media_type="text/javascript", headers=headers)
            return FileResponse(root / name, headers=headers)

        @router.post("/api/session")
        async def login(request: Request) -> JSONResponse:
            if request.headers.get("authorization"):
                actor = self.authenticate(request)
                account = self.accounts.actor_account(actor.actor_id)
            else:
                if request.headers.get("x-pastport-edit") != "1" or request.headers.get(
                    "origin"
                ) not in (None, str(request.base_url).rstrip("/")):
                    raise ServiceError("ORGANIZER_ORIGIN_INVALID", "登录请求来源不合法。", 403)
                address = request.client.host if request.client is not None else "unknown"
                now = time.monotonic()
                self.failed_logins = {
                    key: [stamp for stamp in stamps if stamp > now - 60]
                    for key, stamps in self.failed_logins.items()
                    if any(stamp > now - 60 for stamp in stamps)
                }
                if len(self.failed_logins.get(address, ())) >= 5 or len(self.failed_logins) >= 1000:
                    raise ServiceError("LOGIN_RATE_LIMIT", "登录尝试过于频繁，请稍后再试。", 429)
                try:
                    credentials = await read_body(request, OrganizerPasswordLogin)
                except ValidationError as error:
                    raise ServiceError("LOGIN_INVALID", "请填写有效的账号和密码。", 422) from error
                try:
                    async with self.password_slots:
                        account = await asyncio.to_thread(
                            self.accounts.password,
                            credentials.username,
                            credentials.password.get_secret_value(),
                        )
                except ServiceError as error:
                    if error.code == "AUTHENTICATION_INVALID":
                        self.failed_logins.setdefault(address, []).append(now)
                    raise
                self.failed_logins.pop(address, None)
                actor = account.actor
            if not {"editor", "operator"}.intersection(actor.roles):
                raise ServiceError("ORGANIZER_FORBIDDEN", "此账户没有制作权限。", 403)
            return self.issue_session(request, account)

        @router.get("/api/access")
        async def access(request: Request) -> JSONResponse:
            local = (
                request.client is not None
                and request.client.host in ("127.0.0.1", "::1")
                and request.url.hostname in ("localhost", "127.0.0.1", "::1")
            )
            return JSONResponse(
                {"username": "admin", "setup_required": local and self.accounts.setup_available()},
                headers={"Cache-Control": "no-store"},
            )

        @router.post("/api/admin-setup")
        async def admin_setup(request: Request) -> JSONResponse:
            local = (
                request.client is not None
                and request.client.host in ("127.0.0.1", "::1")
                and request.url.hostname in ("localhost", "127.0.0.1", "::1")
            )
            if (
                not local
                or request.headers.get("x-pastport-edit") != "1"
                or request.headers.get("origin") not in (None, str(request.base_url).rstrip("/"))
            ):
                raise ServiceError(
                    "ADMIN_SETUP_FORBIDDEN", "管理员初始化仅允许在本机制作页完成。", 403
                )
            try:
                body = await read_body(request, OrganizerAdminSetup)
            except ValidationError as error:
                raise ServiceError(
                    "ADMIN_SETUP_INVALID", "请填写有效密码及确认密码。", 422
                ) from error
            if body.password.get_secret_value() != body.password_confirmation.get_secret_value():
                raise ServiceError("ADMIN_SETUP_INVALID", "两次密码不一致。", 422)
            async with self.password_slots:
                account = await asyncio.to_thread(
                    self.accounts.initialize_admin, body.password.get_secret_value()
                )
            return self.issue_session(request, account)

        @router.delete("/api/session")
        async def logout(request: Request) -> Response:
            self.actor(request)
            self.sessions.pop(request.cookies.get("pastport_organizer", ""), None)
            response = Response(status_code=204)
            response.delete_cookie("pastport_organizer", path="/organizer")
            return response

        @router.get("/api/workspace")
        async def workspace(request: Request) -> JSONResponse:
            value = await asyncio.to_thread(self.service.workspace, self.actor(request))
            return JSONResponse(
                value.model_dump(mode="json") if value else None,
                headers={"Cache-Control": "no-store"},
            )

        @router.post("/api/workspace")
        async def select_workspace(request: Request) -> JSONResponse:
            actor = self.actor(request)
            selection = await read_body(request, OrganizerSelection)
            value = await asyncio.to_thread(
                self.service.select_workspace, selection.source_id, actor
            )
            return JSONResponse(
                value.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.get("/api/storage")
        async def storage(request: Request) -> JSONResponse:
            actor = self.actor(request)
            if not {"editor", "operator"}.intersection(actor.roles):
                raise ServiceError("ORGANIZER_FORBIDDEN", "此账户没有制作权限。", 403)
            root = self.service.store.directory.resolve()
            value = OrganizerStorageView(
                cache_directory=root,
                uploads_directory=root / "uploads",
                jobs_directory=root / "jobs",
            )
            return JSONResponse(
                value.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.api_route(
            "/api/review/{source_id}/environment/{view}/{relative:path}", methods=["GET", "POST"]
        )
        async def review_environment(
            source_id: str, view: int, relative: str, request: Request
        ) -> Response:
            actor = self.actor(request)
            source = self.service.source(source_id, actor)
            gateway = self.service.reviews
            if gateway is None:
                raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
            body: bytes | None = None
            if request.method == "POST":
                chunks = bytearray()
                async for chunk in request.stream():
                    chunks.extend(chunk)
                    if len(chunks) > 128000:
                        raise ServiceError("REVIEW_REQUEST_LIMIT", "编辑请求超过读取范围。", 413)
                body = bytes(chunks)
            bound = self.service.bound_review_source(source, actor)
            production = self.service.request(source)
            if body is not None:
                async with self.service.submission:
                    if any(
                        job.status in ("queued", "running", "awaiting_external")
                        for job in self.service.jobs(actor)
                    ):
                        raise ServiceError(
                            "ORGANIZER_BUSY", "请等待制作完成，再调整环境输入。", 409
                        )
                    value = await asyncio.to_thread(
                        gateway.environment,
                        bound,
                        production,
                        view,
                        relative,
                        request.url.query,
                        body,
                        actor.actor_id,
                        str(request.base_url),
                    )
            else:
                value = await asyncio.to_thread(
                    gateway.environment,
                    bound,
                    production,
                    view,
                    relative,
                    request.url.query,
                    body,
                    actor.actor_id,
                    str(request.base_url),
                )
            headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
            if value.media_type == "text/html":
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-"
                    "unsafe-eval'; worker-src 'self' blob:; style-src 'unsafe-inl"
                    "ine'; img-src 'self' data: blob:; connect-src 'self' blob:; "
                    "object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
                )
            if value.path is not None:
                return FileResponse(value.path, headers=headers)
            return Response(
                value.body or b"",
                status_code=value.status,
                media_type=value.media_type,
                headers=headers,
            )

        @router.get("/api/review/{source_id}/workbench/")
        async def native_review_page(source_id: str, request: Request) -> HTMLResponse:
            actor = self.actor(request)
            source = self.service.source(source_id, actor)
            gateway = self.service.reviews
            if gateway is None:
                raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
            value = await asyncio.to_thread(
                gateway.workbench,
                self.service.bound_review_source(source, actor),
                self.service.request(source),
                actor.actor_id,
                f"/organizer/api/review/{source_id}/workbench",
            )
            return HTMLResponse(
                value,
                headers={
                    "Cache-Control": "no-store",
                    "Content-Security-Policy": (
                        "default-src 'self'; script-src 'self' 'unsafe-inline'; style"
                        "-src 'unsafe-inline'; img-src 'self' data:; connect-src 'sel"
                        "f'; object-src 'none'; base-uri 'none'; frame-ancestors 'sel"
                        "f'"
                    ),
                },
            )

        @router.get("/api/review/{source_id}/workbench/data")
        async def native_review_data(source_id: str, request: Request) -> Response:
            actor = self.actor(request)
            source = self.service.source(source_id, actor)
            gateway = self.service.reviews
            if gateway is None:
                raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
            value = await asyncio.to_thread(
                gateway.workbench_data, self.service.bound_review_source(source, actor)
            )
            return Response(
                value, media_type="application/json", headers={"Cache-Control": "no-store"}
            )

        @router.post("/api/review/{source_id}/workbench/save-review")
        async def native_review_save(source_id: str, request: Request) -> JSONResponse:
            body = await read_body(request, NativeReviewWrite)
            await self.service.save_review(
                source_id,
                self.actor(request),
                body.object_id,
                ReviewChange(
                    kind="review",
                    expected_version=body.version,
                    image=body.image,
                    text=body.text,
                    note=body.note,
                ),
            )
            return JSONResponse({"saved": True})

        @router.post("/api/review/{source_id}/workbench/save-introduction")
        async def native_introduction_save(source_id: str, request: Request) -> JSONResponse:
            body = await read_body(request, NativeIntroductionWrite)
            await self.service.save_review(
                source_id,
                self.actor(request),
                body.object_id,
                ReviewChange(
                    kind="introduction", expected_version=body.version, content=body.content
                ),
            )
            return JSONResponse({"saved": True})

        @router.get("/api/review/{source_id}/workbench/media/{relative:path}")
        async def native_review_image(
            source_id: str, relative: str, request: Request
        ) -> FileResponse:
            actor = self.actor(request)
            source = self.service.source(source_id, actor)
            gateway = self.service.reviews
            if gateway is None:
                raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
            path = await asyncio.to_thread(
                gateway.workbench_media, self.service.bound_review_source(source, actor), relative
            )
            if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                raise ServiceError("REVIEW_ASSET_INVALID", "此文件不是审核图片。", 422)
            return FileResponse(
                path, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
            )

        @router.get("/api/review/{source_id}")
        async def review(source_id: str, request: Request) -> JSONResponse:
            value = await asyncio.to_thread(
                self.service.review_view, source_id, self.actor(request)
            )
            return JSONResponse(
                value.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.post("/api/review/{source_id}/objects/{number}")
        async def edit_review(source_id: str, number: int, request: Request) -> JSONResponse:
            value = await self.service.save_review(
                source_id, self.actor(request), number, await read_body(request, ReviewChange)
            )
            return JSONResponse(
                value.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )

        @router.post("/api/review/{source_id}/apply")
        async def apply_review(source_id: str, request: Request) -> JSONResponse:
            body = await read_body(request, ReviewAcknowledgment)
            identifier = await self.service.apply_review(
                source_id, self.actor(request), body.revision
            )
            return JSONResponse({"source_id": identifier})

        @router.get("/api/review/{source_id}/media/{asset_id}")
        async def review_media(source_id: str, asset_id: str, request: Request) -> FileResponse:
            actor = self.actor(request)
            source = self.service.source(source_id, actor)
            gateway = self.service.reviews
            if gateway is None:
                raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
            target = await asyncio.to_thread(
                gateway.media,
                self.service.bound_review_source(source, actor),
                self.service.request(source),
                asset_id,
            )
            if target.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".pdf", ".idml"):
                raise ServiceError("REVIEW_ASSET_INVALID", "此文件不能作为审核图片展示。", 422)
            return FileResponse(
                target,
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "sandbox",
                },
            )

        @router.post("/api/sources/{source_id}/story-compatibility")
        async def check_story_reuse(source_id: str, request: Request) -> JSONResponse:
            identifier = await self.service.check_story_reuse(source_id, self.actor(request))
            return JSONResponse({"source_id": identifier}, headers={"Cache-Control": "no-store"})

        @router.post("/api/sources/{source_id}/confirm-story-reuse")
        async def confirm_story_reuse(source_id: str, request: Request) -> JSONResponse:
            actor = self.actor(request)
            body = await read_body(request, StoryReuseConfirmation)
            identifier = await self.service.check_story_reuse(source_id, actor, body)
            return JSONResponse({"source_id": identifier}, headers={"Cache-Control": "no-store"})

        @router.get("/api/sources")
        async def sources(
            request: Request,
            active_source_id: str | None = None,
            default_only: bool = False,
            metadata_only: bool = False,
        ) -> JSONResponse:
            values = await asyncio.to_thread(
                self.service.sources,
                self.actor(request),
                active_source_id,
                default_only,
                metadata_only,
            )
            return JSONResponse(
                [value.model_dump(mode="json") for value in values],
                headers={"Cache-Control": "no-store"},
            )

        @router.get("/api/jobs")
        async def jobs(request: Request) -> JSONResponse:
            actor = self.actor(request)
            return JSONResponse(
                [
                    self.service.job(j.job_id, actor).model_dump(mode="json")
                    for j in self.service.jobs(actor)
                ],
                headers={"Cache-Control": "no-store"},
            )

        @router.post("/api/jobs/import-delivery", status_code=201)
        async def delivery(request: Request, filename: str) -> JSONResponse:
            actor = self.actor(request)
            name = delivery_name(filename)
            self.service.authorize(actor, name)
            with TemporaryDirectory(prefix="pastport-delivery-") as temporary:
                archive = Path(temporary) / "delivery.tar.gz"
                size = 0
                with archive.open("wb") as stream:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ServiceError("DELIVERY_TOO_LARGE", "交付包不能超过 2 GiB。", 413)
                        stream.write(chunk)
                async with self.service.submission:
                    operation = asyncio.create_task(
                        asyncio.to_thread(
                            import_delivery, self.service.store, actor.actor_id, name, archive
                        )
                    )
                    try:
                        job = await asyncio.shield(operation)
                    except asyncio.CancelledError:
                        await operation
                        raise
            return JSONResponse(job.model_dump(mode="json"), status_code=201)

        @router.post("/api/jobs", status_code=202)
        async def start(request: Request) -> JSONResponse:
            job = await self.service.start(
                self.actor(request),
                await read_body(request, OrganizerStart),
                request.headers.get("idempotency-key", ""),
            )
            return JSONResponse(
                job.model_dump(mode="json"), status_code=202, headers={"Cache-Control": "no-store"}
            )

        @router.get("/api/jobs/{job_id}")
        async def job(job_id: str, request: Request) -> JSONResponse:
            return JSONResponse(
                self.service.job(job_id, self.actor(request)).model_dump(mode="json"),
                headers={"Cache-Control": "no-store"},
            )

        @router.post("/api/jobs/{job_id}/continue", status_code=202)
        async def recover(job_id: str, request: Request) -> JSONResponse:
            recovery = await read_body(request, OrganizerRecovery)
            value = await self.service.recover(job_id, self.actor(request), recovery)
            return JSONResponse(value.model_dump(mode="json"), status_code=202)

        @router.get("/api/jobs/{job_id}/open-mounted")
        async def open_mounted(job_id: str, request: Request) -> RedirectResponse:
            job = self.service.job(job_id, self.actor(request))
            root = self.service.directory(job.job_id) / "mounted-review" / "scene"
            if not job.mounted_preview_ready or not (root / "scene3d/attachment.json").is_file():
                raise ServiceError("ORGANIZER_RESULT_UNAVAILABLE", "3D 审核预览尚未就绪。", 404)
            if self.mounted_previews is None:
                self.mounted_previews = SDKMountedPreviewPool()
            port = await self.mounted_previews.ensure(root)
            return RedirectResponse(
                f"http://127.0.0.1:{port}/scene3d/index.html",
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )

        @router.get("/api/jobs/{job_id}/open")
        async def open_preview(job_id: str, request: Request) -> RedirectResponse:
            job = self.service.job(job_id, self.actor(request))
            if job.status != "completed" or not job.result_ready:
                raise ServiceError("ORGANIZER_RESULT_UNAVAILABLE", "制作产物尚未就绪。", 409)
            url = await self.previews.ensure(self.service.game_directory(job))
            return RedirectResponse(
                url, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
            )

        @router.get("/api/jobs/{job_id}/preview/{relative:path}")
        async def preview(job_id: str, relative: str, request: Request) -> FileResponse:
            value = self.service.job(job_id, self.actor(request))
            if value.status != "completed" or not value.result_ready:
                raise ServiceError("ORGANIZER_RESULT_UNAVAILABLE", "制作产物尚未就绪。", 409)
            root = self.service.game_directory(value)
            target = (root / (relative or "index.html")).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                raise ServiceError("ORGANIZER_NOT_FOUND", "找不到此产物。", 404)
            return FileResponse(
                target,
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "sandbox; default-src 'none'",
                },
            )

        @router.post("/api/materials")
        async def project(request: Request) -> JSONResponse:
            value = self.service.create_project(
                self.actor(request), await read_body(request, OrganizerProjectCreate)
            )
            return JSONResponse(value.model_dump(mode="json"), status_code=201)

        @router.get("/api/materials")
        async def projects(request: Request) -> JSONResponse:
            actor = self.actor(request)
            from pastport.domain.organizer import OrganizerMaterials

            values = [
                value.model_dump(mode="json")
                for value in self.service.store.list("materials", OrganizerMaterials)
                if value.owner_id == actor.actor_id
                and (actor.project_ids is None or value.project_id in actor.project_ids)
            ]
            return JSONResponse(values, headers={"Cache-Control": "no-store"})

        @router.post("/api/materials/{project_id}/jobs", status_code=202)
        async def start_uploads(project_id: str, request: Request) -> JSONResponse:
            value = await self.service.start_uploaded(
                self.actor(request),
                project_id,
                await read_body(request, UploadedProductionStart),
                request.headers.get("idempotency-key", ""),
            )
            return JSONResponse(
                value.model_dump(mode="json"),
                status_code=202,
                headers={"Cache-Control": "no-store"},
            )

        @router.get("/api/jobs/{job_id}/mapping.pdf")
        async def mapping_pdf(job_id: str, request: Request) -> FileResponse:
            job = self.service.job(job_id, self.actor(request))
            root = self.service.directory(job.job_id)
            receipt = root / "native-result.json"
            if job.input_kind != "uploads" or not receipt.is_file():
                raise ServiceError("MAPPING_NOT_READY", "映射文档尚未就绪。", 404)
            value = NativePreparedInputs.model_validate_json(receipt.read_bytes())
            target = value.mapping_pdf
            if (
                target is None
                or not target.resolve().is_relative_to((root / "native").resolve())
                or not target.is_file()
            ):
                raise ServiceError("MAPPING_NOT_READY", "映射文档尚未就绪。", 404)
            return FileResponse(
                target,
                media_type="application/pdf",
                filename="mapping.pdf",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )

        @router.get("/api/materials/{project_id}")
        async def materials(project_id: str, request: Request) -> JSONResponse:
            value = self.service.materials(self.actor(request), project_id)
            return JSONResponse(
                {
                    "materials": value.model_dump(mode="json"),
                    "plan": self.service.plan(
                        value, connected=self.service.uploads_enabled
                    ).model_dump(mode="json"),
                }
            )

        @router.post("/api/materials/{project_id}/files")
        async def upload(
            project_id: str,
            request: Request,
            role: Literal[
                "original_pdf",
                "photos",
                "mapping_pdf",
                "tour",
                "matched_vr",
                "mounted_3d",
                "scene_splat",
                "scene_mesh",
                "original_idml",
                "historical_links",
            ],
            filename: str,
        ) -> JSONResponse:
            actor = self.actor(request)
            if (
                not filename.strip()
                or len(filename) > 240
                or any(c in filename for c in ("/", "\\", "\x00"))
            ):
                raise ServiceError("ORGANIZER_FILENAME_INVALID", "文件名无效。", 422)
            async with self.service.submission:
                material = self.service.materials(actor, project_id)
                allowed = {
                    "raw": {"original_pdf", "photos", "tour"},
                    "mapping": {"original_pdf", "mapping_pdf", "tour"},
                    "vr": {"original_pdf", "matched_vr"},
                    "3d": {"original_pdf", "mounted_3d"},
                    "idml3d": {
                        "original_idml",
                        "historical_links",
                        "photos",
                        "scene_splat",
                        "scene_mesh",
                    },
                    "raw3d": {"original_pdf", "photos", "scene_splat", "scene_mesh"},
                }[material.entry_level]
                if role not in allowed:
                    raise ServiceError(
                        "ORGANIZER_ROLE_MISMATCH", "此材料不属于选定的制作起点。", 422
                    )
                if role != "photos" and any(file.role == role for file in material.files):
                    raise ServiceError(
                        "ORGANIZER_ROLE_DUPLICATE", "此类材料已上传；请使用新项目替换输入。", 409
                    )
                if len(material.files) >= 200:
                    raise ServiceError("ORGANIZER_FILE_LIMIT", "项目文件数量超过限制。", 413)
                total = sum(item.size_bytes for item in material.files)
                maximum = min(
                    (6 if material.entry_level == "idml3d" else 4) * 1024**3 - total,
                    (
                        32
                        if role == "original_idml"
                        else 3072
                        if role == "historical_links"
                        else 512
                        if role in ("original_pdf", "mapping_pdf")
                        else 2048
                    )
                    * 1024**2,
                )
                file_id = uuid4().hex
                directory = (
                    self.service.store.directory
                    / "uploads"
                    / hashlib.sha256((actor.actor_id + ":" + project_id).encode()).hexdigest()
                )
                directory.mkdir(parents=True, exist_ok=True)
                target = directory / file_id
                size, digest, header = 0, hashlib.sha256(), b""
                try:
                    with target.open("xb") as stream:
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > maximum:
                                raise ServiceError(
                                    "ORGANIZER_UPLOAD_LIMIT", "文件或项目上传量超过限制。", 413
                                )
                            header = (header + chunk)[:1024]
                            digest.update(chunk)
                            await asyncio.to_thread(stream.write, chunk)
                    if size == 0 or (
                        role in ("original_pdf", "mapping_pdf") and b"%PDF-" not in header
                    ):
                        raise ServiceError("ORGANIZER_UPLOAD_INVALID", "文件为空或不是 PDF。", 422)
                    if role == "original_idml" and (
                        not filename.lower().endswith(".idml") or not header.startswith(b"PK")
                    ):
                        raise ServiceError(
                            "IDML_UPLOAD_INVALID", "请上传有效IDML压缩结构文件。", 422
                        )
                    if role == "historical_links" and (
                        not filename.lower().endswith(".zip") or not header.startswith(b"PK")
                    ):
                        raise ServiceError("IDML_LINKS_INVALID", "历史配图请上传Links ZIP。", 422)
                    file = OrganizerFile(
                        file_id=file_id,
                        role=role,
                        filename=filename,
                        sha256=digest.hexdigest(),
                        size_bytes=size,
                    )
                    updated = material.model_copy(update={"files": (*material.files, file)})
                    self.service.store.save("materials", actor.actor_id + ":" + project_id, updated)
                    return JSONResponse(file.model_dump(mode="json"), status_code=201)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise

        return router
