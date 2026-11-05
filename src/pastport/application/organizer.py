"""Durable private Organizer jobs, with explicit provider-free replay and recovery."""

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pastport.application.models import Actor, ServiceError
from pastport.application.organizer_cache import CachedBundleValidator, OrganizerCachedBundle
from pastport.application.reliability import BudgetSnapshot
from pastport.application.story_authoring import StoryAuthoringCheck
from pastport.domain.common import CanonicalSerializer
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import (
    OrganizerCatalog,
    OrganizerNativeProgress,
    OrganizerJob,
    OrganizerMaterials,
    OrganizerPlan,
    OrganizerProjectCreate,
    OrganizerRecovery,
    OrganizerSource,
    OrganizerSourceView,
    OrganizerStart,
    OrganizerWorkspace,
)
from pastport.domain.organizer_inputs import (
    NativeInputRequest,
    RegisteredNativeSource,
    UploadedAsset,
    UploadedProductionStart,
)
from pastport.domain.story_inputs import EnvironmentSnapshot
from pastport.ports.organizer import OrganizerProduction, OrganizerRepository
from pastport.ports.organizer_inputs import OrganizerInputPreparer
from pastport.ports.organizer_review import OrganizerReviewGateway
from pastport.ports.story_reuse import StoryReusePort
from pastport.domain.story_reuse import StoryReuseConfirmation, StoryReuseDecision, StoryReuseReport
from pastport.application.story_authoring import StoryInputLock
from pastport.domain.organizer_review import (
    OrganizerReviewBinding, OrganizerReviewView, ReviewChange,
)

logger = logging.getLogger(__name__)


class OrganizerService:
    def __init__(
        self,
        store: OrganizerRepository,
        catalog: OrganizerCatalog,
        production: OrganizerProduction,
        *,
        input_preparer: OrganizerInputPreparer | None = None,
        player_assets: Path | None = None,
        reviews: OrganizerReviewGateway | None = None,
        story_reuse: StoryReusePort | None = None,
    ) -> None:
        ids = [source.source_id for source in catalog.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate Organizer source IDs")
        defaults = [source for source in catalog.sources if source.is_default]
        if len(defaults) > 1 or any(source.bundle_file is None for source in defaults):
            raise ValueError("A default must identify exactly one complete registered cache bundle")
        self.store, self.catalog, self.production = store, catalog, production
        self.tasks: set[asyncio.Task[None]] = set()
        self.submission = asyncio.Lock()
        self.input_preparer, self.player_assets = input_preparer, player_assets
        self.closing = asyncio.Event()
        self.reviews = reviews
        self.story_reuse = story_reuse

    @staticmethod
    def authorize(actor: Actor, project_id: str) -> None:
        if not {"editor", "operator"}.intersection(actor.roles) or (
            actor.project_ids is not None and project_id not in actor.project_ids
        ):
            raise ServiceError("ORGANIZER_FORBIDDEN", "没有此项目的制作权限。", 403)

    def startup(self) -> None:
        # A process restart never redispatches a possibly charged generation.
        for job in self.store.list("job", OrganizerJob):
            if job.status in ("running", "queued", "awaiting_external"):
                self.store.save(
                    "job",
                    job.job_id,
                    job.model_copy(
                        update={
                            "status": "recovery_required",
                            "message": "服务中断；请先查看已保存步骤，再确认是否继续。",
                        }
                    ),
                )

    async def close(self) -> None:
        self.closing.set()
        if self.input_preparer is not None:
            await asyncio.to_thread(self.input_preparer.close)
        if self.tasks:
            await asyncio.gather(*self.tasks)

    def source(self, source_id: str, actor: Actor) -> OrganizerSource:
        for source in self.available_sources(actor):
            if source.source_id == source_id:
                self.authorize(actor, source.project_id)
                return source
        raise ServiceError("ORGANIZER_SOURCE_UNKNOWN", "找不到已登记的可复用材料。", 404)

    @staticmethod
    def request(source: OrganizerSource) -> GameMakingRequest:
        request = GameMakingRequest.model_validate_json(source.request_file.read_bytes())
        request = request.model_copy(
            update={
                name: (source.request_file.parent / value).resolve()
                for name, value in request
                if isinstance(value, Path)
            }
        )
        if source.bundle_file is not None:
            CachedBundleValidator.validate(source.bundle_file, request)
        snapshot = EnvironmentSnapshot.model_validate_json(request.environment.read_bytes())
        if snapshot.project_id != source.project_id:
            raise ServiceError("ORGANIZER_PROJECT_MISMATCH", "登记项目与环境来源不一致。", 409)
        return request

    def workspace(self, actor: Actor) -> OrganizerWorkspace | None:
        # Repository keys scope the selection to the authenticated account.
        try:
            value = self.store.get("workspace", actor.actor_id, OrganizerWorkspace)
        except ServiceError as error:
            if error.code != "ORGANIZER_NOT_FOUND":
                raise
        else:
            source = self.source(value.source_id, actor)
            return self._workspace(source)
        for job in self.jobs(actor):
            if job.input_kind == "uploads" and job.prepared_source_id and job.status in (
                "environment_ready", "story_ready", "completed"
            ):
                return self._workspace(self.source(job.prepared_source_id, actor))
        return None

    def _workspace(self, source: OrganizerSource) -> OrganizerWorkspace:
        request = self.request(source)
        return OrganizerWorkspace(project_id=source.project_id, source_id=source.source_id,
                                  story_ready=self.saved_ready(request))

    def select_workspace(self, source_id: str, actor: Actor) -> OrganizerWorkspace:
        source = self.source(source_id, actor)
        selected = self._workspace(source)
        self.store.save("workspace", actor.actor_id, selected)
        return selected

    @staticmethod
    def fingerprint(request: GameMakingRequest) -> str:
        digest = hashlib.sha256()
        count, total = 0, 0
        for name, value in request:
            if not isinstance(value, Path) or name == "output_directory":
                continue
            if value.is_symlink() or not value.exists():
                raise ServiceError("ORGANIZER_INPUT_MISSING", "登记材料缺失或是不允许的链接。", 409)
            paths = sorted(value.rglob("*")) if value.is_dir() else [value]
            for path in paths:
                if path.is_symlink():
                    raise ServiceError("ORGANIZER_INPUT_LINK", "材料中有未登记的文件链接。", 409)
                if not path.is_file() or path.name.endswith((".lock", ".pyc")):
                    continue
                count += 1
                total += path.stat().st_size
                if count > 20000 or total > 8 * 1024**3:
                    raise ServiceError("ORGANIZER_INPUT_LIMIT", "登记材料超过读取范围。", 413)
                digest.update(name.encode())
                digest.update(
                    str(path.relative_to(value) if value.is_dir() else path.name).encode()
                )
                with path.open("rb") as stream:
                    digest.update(hashlib.file_digest(stream, "sha256").digest())
        digest.update(request.brief.encode())
        return digest.hexdigest()

    def sources(self, actor: Actor, active_source_id: str | None = None, default_only: bool = False, metadata_only: bool = False) -> tuple[OrganizerSourceView, ...]:
        result: list[OrganizerSourceView] = []
        candidates: tuple[OrganizerSource, ...]
        if active_source_id is not None:
            candidates=(self.source(active_source_id,actor),)
        else:
            candidates=tuple(source for source in self.available_sources(actor)
                             if not default_only or source.is_default)
        for source in candidates:
            try:
                self.authorize(actor, source.project_id)
            except ServiceError:
                continue
            if metadata_only:
                result.append(OrganizerSourceView(source_id=source.source_id,title=source.title,
                    project_id=source.project_id,ready=False,is_default=source.is_default,
                    message="项目目录；选中后单独检查资源。"))
                continue
            try:
                request = self.request(source)
                fingerprint = self.fingerprint(request)
                self.production.validate(request)
                reuse_report = self.story_reuse_report(source, request)
                result.append(
                    OrganizerSourceView(
                        source_id=source.source_id,
                        title=source.title,
                        project_id=source.project_id,
                        ready=True,
                        reuse_ready=self.saved_ready(request),
                        reuse_checked=self.saved_ready(request) or bool(reuse_report and reuse_report.compatibility_version==1) or self.story_reuse is None,
                        reuse_confirmation_sha256=CanonicalSerializer.digest(reuse_report) if reuse_report and reuse_report.status=="needs_confirmation" else None,
                        reuse_changes=reuse_report.introduction_changes if reuse_report else (),
                        reuse_issues=reuse_report.issues if reuse_report else (),
                        complete_bundle=source.bundle_file is not None,
                        review_ready=self.review_input_ready(source.source_id, actor),
                        is_default=source.is_default,
                        message=(
                            "来源与资源检查通过；可复用，也可重新生成故事。"
                            if self.saved_ready(request)
                            else "环境已准备，尚无完整故事；请选择重新生成。"
                        ),
                        input_sha256=fingerprint,
                    )
                )
            except (OSError, ValueError, ServiceError) as error:
                logger.warning(
                    "Organizer source rejected: %s (%s)", source.source_id, type(error).__name__
                )
                result.append(
                    OrganizerSourceView(
                        source_id=source.source_id,
                        title=source.title,
                        project_id=source.project_id,
                        ready=False,
                        is_default=source.is_default,
                        message="登记材料检查未通过；维护者需核对来源、文件和版本。",
                    )
                )
        return tuple(result)

    def jobs(self, actor: Actor) -> tuple[OrganizerJob, ...]:
        return tuple(
            job
            for job in self.store.list("job", OrganizerJob)
            if job.owner_id == actor.actor_id
            and (actor.project_ids is None or job.project_id in actor.project_ids)
        )

    def job(self, job_id: str, actor: Actor) -> OrganizerJob:
        job = self.store.get("job", job_id, OrganizerJob)
        self.authorize(actor, job.project_id)
        if job.owner_id != actor.actor_id:
            raise ServiceError("ORGANIZER_FORBIDDEN", "没有此制作记录的权限。", 403)
        native_stages = tuple(
            path.stem
            for path in sorted((self.directory(job_id) / "native/native-receipts").glob("*.json"))
        )
        stages = native_stages + tuple(
            name
            for name in ("story", "gameplay", "presentation", "assembly")
            if (self.game_directory(job).parent / "receipts" / f"{name}.json").is_file()
        )
        issues = job.issues
        if job.mode == "regenerate" and job.status in ("failed", "recovery_required"):
            path = self.directory(job_id) / "fresh-story/story-check.json"
            if path.is_file():
                try:
                    issues = StoryAuthoringCheck.model_validate_json(path.read_bytes()).issues
                except (OSError, ValueError):
                    logger.warning("Organizer check receipt unavailable: %s", job_id)
        message = job.message
        progress_path = self.directory(job_id) / "native/evidence/progress.json"
        if job.status in ("running", "failed", "recovery_required") and progress_path.is_file():
            try:
                progress = OrganizerNativeProgress.model_validate_json(progress_path.read_bytes())
                labels = {"idml_import": "读取IDML与历史配图", "idml_mapping": "匹配IDML文物与介绍", "idml_mapping_ready": "IDML映射已完成，正在交接3D", "ingest_photos": "读取PDF与照片", "recognize_photos": "识别物件",
                          "recognizing_photos": "识别物件", "photo_selection_complete": "物件选择完成",
                          "map_pdf": "匹配PDF史料", "evidence": "核验史料", "export_mapping": "生成映射PDF"}
                if job.status == "running":
                    message = labels.get(progress.phase, message)
                    if progress.phase in ("recognizing_photos", "photo_selection_complete"):
                        message += (
                            f" · 已处理 {progress.completed_calls} 批"
                            f" · 已识别 {progress.recognized_objects} 个物件"
                        )
                elif progress.phase == "photo_inventory_incomplete":
                    message = (
                        f"照片识别第 {progress.completed_calls + 1} 批覆盖不足，"
                        f"此前已处理 {progress.completed_calls} 批。"
                        "已保留模型回执。"
                    )
            except (OSError, ValueError):
                logger.warning("Organizer progress unavailable")
        if job.status == "running" and job.input_kind == "uploads":
            # Evidence progress remains on disk after export; completed receipts
            # take precedence so the UI cannot keep reporting PDF work in 3D.
            if "input_handoff" in native_stages:
                message = "环境输入交接中"
            elif "scene3d_1" in native_stages:
                message = "校验3D挂载与环境资料"
            elif "matched_environment" in native_stages:
                message = "挂载3D编号与导航"
            elif "evidence" in native_stages:
                message = "映射PDF已导出，正在匹配环境物件"
        return job.model_copy(
            update={
                "message": message,
                "completed_stages": stages,
                "cache_directory": self.directory(job_id).resolve(),
                "game_directory": self.game_directory(job).resolve() if job.result_ready else None,
                "issues": issues,
                "new_model_calls": self.model_calls(job),
                "error_code": job.error_code if job.status in ("failed", "recovery_required") else None,
            }
        )

    def directory(self, job_id: str) -> Path:
        # IDs read from validated models; do not accept a URL path as a filesystem path.
        return self.store.directory / "jobs" / job_id

    def game_directory(self, job: OrganizerJob) -> Path:
        directory = self.directory(job.job_id)
        pointer = directory / "organizer-production-request.json"
        if not pointer.is_file():
            return directory / "game-3d"
        request = GameMakingRequest.model_validate_json(pointer.read_bytes())
        build = request.output_directory.resolve()
        if not build.is_relative_to(directory.resolve()):
            raise ServiceError("ORGANIZER_BUILD_SCOPE", "制作产物不在本任务目录内。", 409)
        return build / "game-3d"

    async def start(self, actor: Actor, payload: OrganizerStart, key: str) -> OrganizerJob:
        if not key or len(key) > 120 or not all(c.isalnum() or c in "-_.:" for c in key):
            raise ServiceError("ORGANIZER_KEY_REQUIRED", "请提供有效的制作请求标识。", 422)
        source = self.source(payload.source_id, actor)
        if payload.mode == "regenerate" and not payload.authorize_model:
            raise ServiceError(
                "MODEL_AUTHORIZATION_REQUIRED", "重新生成需要明确确认模型调用。", 422
            )
        if payload.mode == "reuse" and (payload.authorize_model or payload.brief is not None):
            raise ServiceError("REUSE_IS_IMMUTABLE", "缓存复用不会修改已保存故事或调用模型。", 422)
        async with self.submission:
            for previous in self.jobs(actor):
                if previous.request_key == key:
                    if previous.payload_sha256 != CanonicalSerializer.digest(payload):
                        raise ServiceError(
                            "ORGANIZER_KEY_CONFLICT", "同一请求标识不能用于不同的制作设置。", 409
                        )
                    return previous
            if any(
                j.status in ("running", "queued", "awaiting_external")
                for j in self.store.list("job", OrganizerJob)
            ):
                raise ServiceError("ORGANIZER_BUSY", "当前已有制作任务，请等待它结束。", 409)
            request = self.request(source)
            if payload.stop_after != "environment" and payload.mode == "reuse" and not self.saved_ready(request):
                raise ServiceError(
                    "SAVED_STORY_MISSING", "此环境尚无完整故事结果，请选择重新生成。", 409
                )
            if self.reviews is not None and payload.stop_after != "environment":
                view = await asyncio.to_thread(self.review_view, source.source_id, actor)
                if not view.snapshot_current:
                    raise ServiceError("REVIEW_SNAPSHOT_STALE", "审核内容已更新，请先应用审核版本，再准备故事。", 409)
            fingerprint = await asyncio.to_thread(self.fingerprint, request)
            await asyncio.to_thread(self.production.validate, request)
            job = OrganizerJob(
                job_id=uuid4().hex,
                owner_id=actor.actor_id,
                project_id=source.project_id,
                source_id=source.source_id,
                mode=payload.mode,
                status="queued",
                message="输入校验通过，等待执行。",
                new_model_calls=0 if payload.mode == "reuse" else None,
                input_sha256=fingerprint,
                request_key=key,
                payload_sha256=CanonicalSerializer.digest(payload),
            )
            directory = self.directory(job.job_id)
            directory.mkdir(parents=True)
            if source.bundle_file is not None:
                (directory / "cache-bundle.json").write_bytes(source.bundle_file.read_bytes())
                bundle = OrganizerCachedBundle.model_validate_json(source.bundle_file.read_bytes())
                (directory / "review-binding.json").write_text(OrganizerReviewBinding(
                    root=bundle.native_import.path.parent,
                    worlds=tuple(world.attachment.path.parent.parent for world in bundle.worlds),
                    import_sha256=bundle.native_import.sha256,
                ).model_dump_json())
            elif source.review_binding_file is not None:
                (directory / "review-binding.json").write_bytes(source.review_binding_file.read_bytes())
            (directory / "organizer-start.json").write_text(payload.model_dump_json())
            (directory / "registered-request.json").write_text(request.model_dump_json())
            self.store.save("job", job.job_id, job)
            self.dispatch(job, request, payload)
            return job

    def dispatch(
        self,
        job: OrganizerJob,
        request: GameMakingRequest,
        start: OrganizerStart,
        *,
        resume: bool = False,
    ) -> None:
        task = asyncio.create_task(asyncio.to_thread(self.execute, job, request, start, resume))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def execute(
        self,
        job: OrganizerJob,
        request: GameMakingRequest,
        start: OrganizerStart,
        resume: bool = False,
    ) -> None:
        try:
            bundle = self.directory(job.job_id) / "cache-bundle.json"
            if bundle.is_file():
                CachedBundleValidator.validate(bundle, request)
            if self.fingerprint(request) != job.input_sha256:
                raise ServiceError(
                    "ORGANIZER_INPUT_CHANGED", "登记材料已改变，不能复用此任务。", 409
                )
            self.store.save(
                "job",
                job.job_id,
                job.model_copy(
                    update={
                        "status": "running",
                        "message": "正在执行真实 SDK 制作流程。",
                    }
                ),
            )
            if start.stop_after == "environment":
                self.store.save("workspace", job.owner_id, OrganizerWorkspace(
                    project_id=job.project_id, source_id=job.source_id,
                    story_ready=self.saved_ready(request),
                ))
                self.store.save("job", job.job_id, job.model_copy(update={
                    "status": "environment_ready", "prepared_source_id": job.source_id,
                    "message": "默认资料与环境已准备，已自动接入资料审核；不会自动生成故事或游戏。",
                    "new_model_calls": 0,
                }))
                return
            asyncio.run(
                self.production.run(request, start, self.directory(job.job_id), resume=resume)
            )
            if start.stop_after == "story":
                pointer = self.directory(job.job_id) / "organizer-production-request.json"
                prepared = self.register_prepared_source(job, pointer, "已准备故事与环境", unique=True)
                if prepared is None:
                    raise ServiceError("STORY_HANDOFF_MISSING", "故事未返回可校验的交接结果。", 409)
                self.store.save("job", job.job_id, job.model_copy(update={
                    "status": "story_ready", "prepared_source_id": prepared,
                    "message": "故事已核对；点击开始制作后才执行玩法、呈现与组包。",
                    "new_model_calls": self.model_calls(job),
                }))
                return
            prepared = self.register_prepared_source(
                job, self.directory(job.job_id) / "organizer-production-request.json",
                "已完成故事与环境，可继续制作", unique=True,
            ) or job.source_id
            self.store.save(
                "job",
                job.job_id,
                job.model_copy(
                    update={
                        "status": "completed",
                        "prepared_source_id": prepared,
                        "message": "制作产物已生成并通过资源检查；不代表史料批准或发布。",
                        "result_ready": True,
                        "error_code": None,
                        "issues": (),
                        "new_model_calls": self.model_calls(job),
                    }
                ),
            )
        except (OSError, ValueError, ServiceError, RuntimeError) as error:
            logger.exception("Organizer job stopped: %s", job.job_id)
            issues: tuple[str, ...] = ()
            check_path = self.directory(job.job_id) / "fresh-story/story-check.json"
            if check_path.is_file():
                try:
                    issues = StoryAuthoringCheck.model_validate_json(check_path.read_bytes()).issues
                except (OSError, ValueError):
                    logger.warning("Organizer check receipt unavailable: %s", job.job_id)
            self.store.save(
                "job",
                job.job_id,
                job.model_copy(
                    update={
                        "error_code": error.code
                        if isinstance(error, ServiceError)
                        else "PRODUCTION_FAILED",
                        "issues": issues,
                        "status": "failed"
                        if issues or start.mode == "reuse"
                        else "recovery_required",
                        "message": "制作停止，已保留结果和回执；请查看恢复摘要，系统不会自动重试模型。",
                        "new_model_calls": self.model_calls(job),
                    }
                ),
            )

    def model_calls(self, job: OrganizerJob) -> int | None:
        if job.mode == "reuse":
            return 0
        start_file = self.directory(job.job_id) / "organizer-start.json"
        if job.input_kind == "registered" and start_file.is_file():
            start = OrganizerStart.model_validate_json(start_file.read_bytes())
            if start.stop_after == "environment":
                return 0
        native_calls = (
            self.input_preparer.model_calls(self.directory(job.job_id) / "native")
            if job.input_kind == "uploads" and self.input_preparer is not None
            else 0
        )
        if native_calls is None:
            return None
        path = self.directory(job.job_id) / "fresh-story/budget.json"
        if not path.is_file():
            return (
                native_calls if job.input_kind == "uploads" and not path.parent.exists() else None
            )
        try:
            budget = BudgetSnapshot.model_validate_json(path.read_bytes())
        except (OSError, ValueError):
            return None
        if any(
            entry.state in ("unknown", "reserved") and entry.reserved.model_requests
            for entry in budget.entries
        ):
            return None
        return native_calls + budget.used.model_requests

    async def recover(
        self, job_id: str, actor: Actor, recovery: OrganizerRecovery | None = None
    ) -> OrganizerJob:
        async with self.submission:
            job = self.job(job_id, actor)
            if job.status not in ("recovery_required", "failed", "awaiting_materials"):
                raise ServiceError("ORGANIZER_NOT_RECOVERABLE", "此任务无需恢复。", 409)
            if job.input_kind == "uploads":
                return await self.recover_uploaded(
                    job, actor, recovery or OrganizerRecovery(confirm_continue=True)
                )
            if job.mode == "regenerate" and not all(
                (self.directory(job_id) / "fresh-story" / name).is_file()
                for name in (
                    "narrative-draft.json",
                    "story-check.json",
                    "input-lock.json",
                    "story.md",
                )
            ):
                raise ServiceError(
                    "MODEL_RECONCILIATION_REQUIRED",
                    "尚未取得完整故事回执；需先核对原调用，不能直接再次发起。",
                    409,
                )
            if any(
                j.status in ("running", "queued", "awaiting_external")
                for j in self.store.list("job", OrganizerJob)
            ):
                raise ServiceError("ORGANIZER_BUSY", "当前已有制作任务。", 409)
            directory = self.directory(job_id)
            request = GameMakingRequest.model_validate_json(
                (directory / "registered-request.json").read_bytes()
            )
            start = OrganizerStart.model_validate_json(
                (directory / "organizer-start.json").read_bytes()
            )
            if await asyncio.to_thread(self.fingerprint, request) != job.input_sha256:
                raise ServiceError("ORGANIZER_INPUT_CHANGED", "材料已改变，请创建新任务。", 409)
            queued = job.model_copy(
                update={"status": "queued", "message": "已确认恢复，复核已保存步骤后继续。"}
            )
            self.store.save("job", job_id, queued)
            self.dispatch(queued, request, start, resume=True)
            return queued

    def create_project(self, actor: Actor, payload: OrganizerProjectCreate) -> OrganizerMaterials:
        self.authorize(actor, payload.project_id)
        key = actor.actor_id + ":" + payload.project_id
        try:
            previous = self.store.get("materials", key, OrganizerMaterials)
        except ServiceError as error:
            if error.status_code != 404:
                raise
        else:
            if previous.entry_level != payload.entry_level:
                raise ServiceError(
                    "ORGANIZER_ENTRY_LOCKED", "已有资料的起点不可直接替换，请另建项目。", 409
                )
            return previous
        result = OrganizerMaterials(
            project_id=payload.project_id, owner_id=actor.actor_id, entry_level=payload.entry_level
        )
        self.store.save("materials", key, result)
        return result

    def materials(self, actor: Actor, project_id: str) -> OrganizerMaterials:
        self.authorize(actor, project_id)
        return self.store.get("materials", actor.actor_id + ":" + project_id, OrganizerMaterials)

    @staticmethod
    def plan(materials: OrganizerMaterials, *, connected: bool = False) -> OrganizerPlan:
        roles = {item.role for item in materials.files}
        required, reused, stages, focus = {
            "raw": (
                ("original_pdf", "photos"),
                (),
                (
                    "evidence.photo_mapping",
                    "environment.environment_build",
                    "environment.scene3d",
                    "story",
                    "gameplay",
                    "presentation",
                    "assembly",
                ),
                ("照片识别", "史料对应与出处"),
            ),
            "mapping": (
                ("original_pdf", "mapping_pdf", "tour"),
                ("mapping_pdf",),
                (
                    "environment.environment_build",
                    "environment.scene3d",
                    "story",
                    "gameplay",
                    "presentation",
                    "assembly",
                ),
                ("映射与原始史料的来源关系", "全景定位"),
            ),
            "vr": (
                ("original_pdf", "matched_vr"),
                ("mapping_pdf", "matched_vr"),
                ("environment.scene3d", "story", "gameplay", "presentation", "assembly"),
                ("已登记热点", "共享审核记录", "导航"),
            ),
            "catalog3d": (
                ("original_pdf", "scene_splat", "scene_mesh"),
                ("scene_splat", "scene_mesh"),
                ("local_scene_import", "catalog_extraction", "catalog_localization", "input_handoff"),
                ("展签原文", "同一实物的外观证据", "3D候选落点", "交接到故事入口"),
            ),
            "idml3d": (
                ("original_idml", "historical_links", "photos", "scene_splat", "scene_mesh"),
                ("scene_splat", "scene_mesh"),
                ("idml_source_import", "local_scene_import", "evidence.idml_mapping", "environment.idml_mount", "input_handoff", "story", "gameplay", "presentation", "assembly"),
                ("IDML原文与图片链接", "跨页图文候选", "文物介绍与精确原文", "3D定位", "不调用Marble"),
            ),
            "raw3d": (
                ("original_pdf", "photos", "scene_splat", "scene_mesh"),
                ("scene_splat", "scene_mesh"),
                ("local_scene_import", "evidence.photo_mapping", "environment.environment_build", "input_handoff", "story", "gameplay", "presentation", "assembly"),
                ("照片与原始史料对应", "导入3D的编号定位", "尺度和坐标待审核", "不调用Marble"),
            ),
            "3d": (
                ("original_pdf", "mounted_3d"),
                ("mapping_pdf", "matched_vr", "mounted_3d"),
                ("story", "gameplay", "presentation", "assembly"),
                ("物件绑定", "空间约束", "导航", "史料来源"),
            ),
        }[materials.entry_level]
        return OrganizerPlan(
            entry_level=materials.entry_level,
            missing_roles=tuple(role for role in required if role not in roles),
            reused=reused,
            stages=stages,
            review_focus=focus,
            generation_connected=connected,
            message="可按此起点启动原生制作；生成服务需本次明确授权。"
            if connected
            else "材料已保存，原生制作资源尚未配置。",
        )

    @staticmethod
    def saved_ready(request: GameMakingRequest) -> bool:
        for proof in (request.saved_story_run / "story-compatibility.json", request.saved_story_run.parent / "story-compatibility.json"):
            if proof.is_file():
                try:
                    if StoryReuseReport.model_validate_json(proof.read_bytes()).status != "compatible":
                        return False
                except (OSError, ValueError):
                    return False
        return all(
            (request.saved_story_run / name).is_file()
            for name in (
                "input-lock.json",
                "narrative-draft.json",
                "story-check.json",
                "budget.json",
            )
        )

    def available_sources(self, actor: Actor) -> tuple[OrganizerSource, ...]:
        dynamic = tuple(
            OrganizerSource(
                source_id=source.source_id,
                title=source.title,
                project_id=source.project_id,
                request_file=source.request_file,
                review_binding_file=source.review_binding_file,
            )
            for source in self.store.list("native_source", RegisteredNativeSource)
            if source.owner_id == actor.actor_id
        )
        return (*self.catalog.sources, *dynamic)

    @property
    def uploads_enabled(self) -> bool:
        return self.input_preparer is not None and self.player_assets is not None

    def _upload_request(
        self,
        actor: Actor,
        material: OrganizerMaterials,
        options: UploadedProductionStart,
        job_id: str,
    ) -> NativeInputRequest:
        if self.player_assets is None:
            raise ServiceError("PLAYER_ASSETS_UNAVAILABLE", "维护者尚未配置共享播放器资源。", 503)
        root = (
            self.store.directory
            / "uploads"
            / hashlib.sha256((actor.actor_id + ":" + material.project_id).encode()).hexdigest()
        )
        return NativeInputRequest(
            project_id=material.project_id,
            owner_id=actor.actor_id,
            job_id=job_id,
            entry_level=material.entry_level,
            options=options,
            shared_player_assets=self.player_assets,
            files=tuple(
                UploadedAsset(
                    file_id=file.file_id,
                    role=file.role,
                    filename=file.filename,
                    sha256=file.sha256,
                    path=root / file.file_id,
                )
                for file in material.files
            ),
        )

    async def start_uploaded(
        self, actor: Actor, project_id: str, options: UploadedProductionStart, key: str
    ) -> OrganizerJob:
        material = self.materials(actor, project_id)
        if material.entry_level == "catalog3d":
            options = options.model_copy(update={"stop_after": "environment"})
        if not self.uploads_enabled:
            raise ServiceError(
                "UPLOAD_PRODUCTION_UNAVAILABLE", "原生制作所需的服务器资源尚未配置。", 503
            )
        if not options.authorize_model:
            raise ServiceError(
                "MODEL_AUTHORIZATION_REQUIRED", "请确认本次材料制作会调用生成服务。", 422
            )
        if not key or len(key) > 120 or not all(c.isalnum() or c in "-_.:" for c in key):
            raise ServiceError("ORGANIZER_KEY_REQUIRED", "请提供有效的制作请求标识。", 422)
        plan = self.plan(material)
        if plan.missing_roles:
            raise ServiceError(
                "MATERIALS_MISSING", "请补齐此起点所需材料：" + "、".join(plan.missing_roles), 422
            )
        async with self.submission:
            digest = CanonicalSerializer.digest(options)
            for old in self.jobs(actor):
                if old.request_key == key:
                    if (
                        old.payload_sha256 != digest
                        or old.project_id != project_id
                        or old.input_kind != "uploads"
                    ):
                        raise ServiceError(
                            "ORGANIZER_KEY_CONFLICT", "同一请求标识不能对应不同制作输入。", 409
                        )
                    return old
            if any(
                job.status in ("queued", "running", "awaiting_external")
                for job in self.store.list("job", OrganizerJob)
            ):
                raise ServiceError("ORGANIZER_BUSY", "当前已有制作任务。", 409)
            job_id = uuid4().hex
            request = self._upload_request(actor, material, options, job_id)
            for asset in request.files:
                if (
                    asset.path.is_symlink()
                    or not asset.path.is_file()
                    or self.file_hash(asset.path) != asset.sha256
                ):
                    raise ServiceError("UPLOADED_INPUT_CHANGED", "上传材料已改变。", 409)
            job = OrganizerJob(
                job_id=job_id,
                owner_id=actor.actor_id,
                project_id=project_id,
                source_id="uploaded-" + job_id,
                mode="regenerate",
                input_kind="uploads", entry_level=material.entry_level,
                status="queued",
                message="已保存本次原生输入快照，等待制作。",
                input_sha256=CanonicalSerializer.digest(request),
                request_key=key,
                payload_sha256=digest,
                new_model_calls=0,
            )
            directory = self.directory(job_id)
            directory.mkdir(parents=True)
            (directory / "native-request.json").write_text(request.model_dump_json(indent=2))
            self.store.save("job", job_id, job)
            self.dispatch_uploaded(job, request)
            return job

    @staticmethod
    def file_hash(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def dispatch_uploaded(self, job: OrganizerJob, request: NativeInputRequest) -> None:
        task = asyncio.create_task(self.execute_uploaded(job, request))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def execute_uploaded(self, job: OrganizerJob, request: NativeInputRequest) -> None:
        preparer = self.input_preparer
        if preparer is None:
            raise ServiceError("UPLOAD_PRODUCTION_UNAVAILABLE", "原生制作服务不可用。", 503)
        output = self.directory(job.job_id)
        native = output / "native"
        try:
            while True:
                self.store.save(
                    "job",
                    job.job_id,
                    job.model_copy(
                        update={"status": "running", "message": "正在按材料起点执行原生SDK步骤。"}
                    ),
                )
                result = await asyncio.to_thread(preparer.prepare, request, native)
                (output / "native-result.json").write_text(result.model_dump_json(indent=2))
                if result.state == "awaiting_materials":
                    self.store.save(
                        "job",
                        job.job_id,
                        job.model_copy(
                            update={
                                "status": "awaiting_materials",
                                "message": result.message,
                                "new_model_calls": self.model_calls(job),
                            }
                        ),
                    )
                    return
                if result.state == "awaiting_external":
                    self.store.save(
                        "job",
                        job.job_id,
                        job.model_copy(
                            update={
                                "status": "awaiting_external",
                                "message": result.message,
                                "new_model_calls": self.model_calls(job),
                            }
                        ),
                    )
                    try:
                        await asyncio.wait_for(self.closing.wait(), timeout=5)
                    except TimeoutError:
                        continue
                    self.store.save(
                        "job",
                        job.job_id,
                        job.model_copy(
                            update={
                                "status": "recovery_required",
                                "message": "服务已停止；恢复时仅核对原服务操作，不重新提交。",
                            }
                        ),
                    )
                    return
                if result.request is None:
                    raise ServiceError(
                        "NATIVE_HANDOFF_MISSING", "原生准备没有返回可校验的输入。", 409
                    )
                prepared_request = result.request
                await asyncio.to_thread(self.production.validate, prepared_request)
                prepared_source = self.register_prepared_source(
                    job, native / "prepared-request.json", "已准备环境，可生成故事", unique=True
                )
                if request.options.stop_after == "environment":
                    if prepared_source is None:
                        raise ServiceError("ENVIRONMENT_HANDOFF_MISSING", "环境交接文件缺失。", 409)
                    self.store.save("job", job.job_id, job.model_copy(update={
                        "status": "environment_ready", "prepared_source_id": prepared_source,
                        "mounted_preview_ready": request.entry_level == "catalog3d" and (
                            native / "scene3d-1/result/scene3d/attachment.json"
                        ).is_file(),
                        "message": result.message + " 尚未调用Story或组包。",
                        "new_model_calls": self.model_calls(job),
                    }))
                    return
                (output / "registered-request.json").write_text(result.request.model_dump_json())
                start = OrganizerStart(
                    source_id=job.source_id,
                    mode="regenerate",
                    authorize_model=True,
                    brief=request.options.brief,
                    target_minutes=request.options.target_minutes,
                )
                (output / "organizer-start.json").write_text(start.model_dump_json())
                self.store.save(
                    "job",
                    job.job_id,
                    job.model_copy(
                        update={
                            "status": "running",
                            "message": "原生输入交接通过，正在执行Story、玩法、呈现和组包。",
                        }
                    ),
                )
                resume = (output / "fresh-story").exists()
                await asyncio.to_thread(
                    lambda: asyncio.run(
                        self.production.run(prepared_request, start, output, resume=resume)
                    )
                )
                completed_source = self.register_prepared_source(
                    job,
                    output / "organizer-production-request.json",
                    "已完成故事与环境，可直接复用",
                    unique=True,
                ) or prepared_source
                self.store.save(
                    "job",
                    job.job_id,
                    job.model_copy(
                        update={
                            "status": "completed",
                            "prepared_source_id": completed_source,
                            "message": "原生材料已自动交接到故事、玩法、呈现与组包。",
                            "new_model_calls": self.model_calls(job),
                            "result_ready": True,
                            "error_code": None,
                            "issues": (),
                        }
                    ),
                )
                return
        except (
            OSError,
            ValueError,
            RuntimeError,
            ImportError,
            sqlite3.Error,
            ServiceError,
        ) as error:
            logger.exception("Uploaded-material production stopped: %s", job.job_id)
            self.store.save(
                "job",
                job.job_id,
                job.model_copy(
                    update={
                        "status": "recovery_required"
                        if self.model_calls(job) is None
                        else "failed",
                        "message": str(error)
                        if isinstance(error, ServiceError)
                        else "原生准备失败，已保留输入和回执。",
                        "error_code": error.code
                        if isinstance(error, ServiceError)
                        else "NATIVE_PREPARATION_FAILED",
                        "new_model_calls": self.model_calls(job),
                    }
                ),
            )

    def register_prepared_source(
        self, job: OrganizerJob, request_file: Path, title: str, *, unique: bool = False
    ) -> str | None:
        if not request_file.is_file():
            return None
        source_id = (
            "prepared-"
            + hashlib.sha256((job.owner_id + ":" + (job.job_id if unique else job.project_id)).encode()).hexdigest()[:32]
        )
        prepared_request = GameMakingRequest.model_validate_json(request_file.read_bytes())
        nested_binding = prepared_request.environment.parent / "review-binding.json"
        if not nested_binding.resolve().is_relative_to(request_file.parent.resolve()):
            nested_binding = request_file.parent / "review-binding.json"
        binding_file = next((path for path in (
            nested_binding,
            request_file.parent / "review-binding.json",
            self.directory(job.job_id) / "review-binding.json",
            self.directory(job.job_id) / "native/review-binding.json",
        ) if path.is_file()), None)
        source = RegisteredNativeSource(
            parent_source_id=job.source_id if job.source_id else None,
            review_binding_file=binding_file,
            owner_id=job.owner_id,
            project_id=job.project_id,
            source_id=source_id,
            title=title + " · " + job.project_id,
            request_file=request_file,
        )
        self.store.save("native_source", source_id, source)
        self.store.save("workspace", job.owner_id, OrganizerWorkspace(
            project_id=job.project_id, source_id=source_id,
            story_ready=self.saved_ready(prepared_request),
        ))
        return source_id

    async def recover_uploaded(
        self, job: OrganizerJob, actor: Actor, recovery: OrganizerRecovery
    ) -> OrganizerJob:
        if any(
            other.status in ("queued", "running", "awaiting_external")
            for other in self.store.list("job", OrganizerJob)
        ):
            raise ServiceError("ORGANIZER_BUSY", "当前已有制作任务。", 409)
        request_file = self.directory(job.job_id) / "native-request.json"
        request = NativeInputRequest.model_validate_json(request_file.read_bytes())
        if job.status == "awaiting_materials":
            material = self.materials(actor, job.project_id)
            incoming = self._upload_request(actor, material, request.options, job.job_id)
            old = {file.file_id: file for file in request.files}
            current = {file.file_id: file for file in incoming.files}
            if any(current.get(key) != value for key, value in old.items()) or any(
                file.role != "tour" for key, file in current.items() if key not in old
            ):
                raise ServiceError(
                    "RECOVERY_INPUT_CHANGED",
                    "只允许补充缺失的360导览；其它材料改变请新建制作。",
                    409,
                )
            request = incoming
        if recovery.authorize_marble:
            if any(
                (self.directory(job.job_id) / "native" / f"scene3d-{index}/request.json").exists()
                for index in (1, 2)
            ):
                if recovery.marble_credit_budget != request.options.marble_credit_budget:
                    raise ServiceError(
                        "MARBLE_GRANT_LOCKED", "已有3D调用记录，不能修改该次授权。", 409
                    )
            request = request.model_copy(
                update={
                    "options": request.options.model_copy(
                        update={
                            "authorize_marble": True,
                            "marble_credit_budget": recovery.marble_credit_budget,
                        }
                    )
                }
            )
        amendment = self.directory(job.job_id) / ("input-amendment-" + uuid4().hex + ".json")
        amendment.write_text(
            json.dumps(
                {
                    "previous_sha256": job.input_sha256,
                    "request": json.loads(request.model_dump_json()),
                    "actor_id": actor.actor_id,
                }
            )
        )
        request_file.write_text(request.model_dump_json())
        queued = job.model_copy(
            update={
                "status": "queued",
                "input_sha256": CanonicalSerializer.digest(request),
                "message": "已确认恢复，核对保存步骤后继续。",
            }
        )
        self.store.save("job", job.job_id, queued)
        self.dispatch_uploaded(queued, request)
        return queued


    def bound_review_source(self, source: OrganizerSource, actor: Actor) -> OrganizerSource:
        current = source
        for _ in range(8):
            if current.bundle_file is not None or current.review_binding_file is not None:
                return current.model_copy(update={"source_id": source.source_id, "title": source.title})
            prepared = GameMakingRequest.model_validate_json(current.request_file.read_bytes())
            binding_file = prepared.environment.parent / "review-binding.json"
            if binding_file.resolve().is_relative_to(current.request_file.parent.resolve()) and binding_file.is_file():
                return current.model_copy(update={"source_id": source.source_id,
                    "title": source.title, "review_binding_file": binding_file})
            start_file = current.request_file.parent / "organizer-start.json"
            if not start_file.is_file():
                break
            start = OrganizerStart.model_validate_json(start_file.read_bytes())
            parent = self.source(start.source_id, actor)
            if parent.project_id != source.project_id or parent.source_id == current.source_id:
                break
            current = parent
        raise ServiceError("REVIEW_NOT_PREPARED", "项目尚未提供审核来源，请先准备环境。", 409)

    def review_view(self, source_id: str, actor: Actor) -> OrganizerReviewView:
        if self.reviews is None:
            raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
        source = self.source(source_id, actor)
        return self.reviews.read(self.bound_review_source(source, actor), self.request(source))

    def review_input_ready(self, source_id: str, actor: Actor) -> bool:
        if self.reviews is None:
            return True
        try:
            return self.review_view(source_id, actor).snapshot_current
        except (OSError, ValueError, ServiceError):
            return False

    async def save_review(self, source_id: str, actor: Actor, number: int, change: ReviewChange) -> OrganizerReviewView:
        if self.reviews is None:
            raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
        async with self.submission:
            if any(job.status in ("queued", "running", "awaiting_external") for job in self.store.list("job", OrganizerJob)):
                raise ServiceError("ORGANIZER_BUSY", "请等待当前制作完成，再修改它的输入资料。", 409)
            source = self.source(source_id, actor)
            await asyncio.to_thread(self.reviews.save, self.bound_review_source(source, actor), self.request(source), number, change, actor.actor_id)
            return await asyncio.to_thread(self.review_view, source_id, actor)

    async def apply_review(self, source_id: str, actor: Actor, revision: str) -> str:
        if self.reviews is None:
            raise ServiceError("REVIEW_UNAVAILABLE", "审核接线尚未配置。", 503)
        async with self.submission:
            if any(job.status in ("queued", "running", "awaiting_external") for job in self.store.list("job", OrganizerJob)):
                raise ServiceError("ORGANIZER_BUSY", "请等待当前制作完成。", 409)
            source = self.source(source_id, actor)
            view = await asyncio.to_thread(self.review_view, source_id, actor)
            if revision != view.revision:
                raise ServiceError("REVIEW_VERSION_CONFLICT", "资料已变化，请重新载入核对。", 409)
            output = self.store.directory / "review-exports" / uuid4().hex
            output.parent.mkdir(parents=True, exist_ok=True)
            prepared = await asyncio.to_thread(self.reviews.export, self.bound_review_source(source, actor), self.request(source), actor.actor_id, output)
            if self.story_reuse is not None:
                prepared = await asyncio.to_thread(self.story_reuse.prepare, self.story_reuse_candidate(source, actor), prepared, output)
                (output / "prepared-request.json").write_text(prepared.model_dump_json())
            identifier = "reviewed-" + output.name
            self.store.save("native_source", identifier, RegisteredNativeSource(
                parent_source_id=source_id,
                owner_id=actor.actor_id, project_id=source.project_id, source_id=identifier,
                title="已应用审核的新环境版本 · " + source.project_id,
                request_file=output / "prepared-request.json", review_binding_file=output / "review-binding.json",
            ))
            return identifier


    @staticmethod
    def story_reuse_report(source: OrganizerSource, request: GameMakingRequest) -> StoryReuseReport | None:
        for path in (request.saved_story_run / "story-compatibility.json", source.request_file.parent / "story-compatibility.json"):
            if path.is_file():
                return StoryReuseReport.model_validate_json(path.read_bytes())
        return None

    def story_reuse_candidate(self, source: OrganizerSource, actor: Actor) -> GameMakingRequest:
        lineage={source.source_id}
        records={item.source_id:item for item in self.store.list("native_source",RegisteredNativeSource)
                 if item.owner_id==actor.actor_id and item.project_id==source.project_id}
        cursor=source.source_id
        while cursor in records and records[cursor].parent_source_id:
            parent=records[cursor].parent_source_id
            if parent is None or parent in lineage:
                break
            lineage.add(parent);cursor=parent
        current_binding=self.story_reuse_binding(source,actor)
        for job in self.jobs(actor):
            if job.project_id != source.project_id or job.status != "story_ready" or not job.prepared_source_id:
                continue
            candidate_source=self.source(job.prepared_source_id,actor)
            if job.source_id not in lineage and (current_binding is None or
                self.story_reuse_binding(candidate_source,actor)!=current_binding):
                continue
            candidate=self.request(candidate_source)
            if self.saved_ready(candidate):
                return candidate
        return self.request(source)

    def story_reuse_binding(self, source: OrganizerSource, actor: Actor) -> OrganizerReviewBinding | None:
        try:
            bound=self.bound_review_source(source,actor)
        except ServiceError as error:
            if error.code=="REVIEW_NOT_PREPARED":
                return None
            raise
        if bound.review_binding_file is not None:
            binding=OrganizerReviewBinding.model_validate_json(bound.review_binding_file.read_bytes())
        elif bound.bundle_file is not None:
            bundle=OrganizerCachedBundle.model_validate_json(bound.bundle_file.read_bytes())
            binding=OrganizerReviewBinding(root=bundle.native_import.path.parent,
                worlds=tuple(w.attachment.path.parent.parent for w in bundle.worlds),
                import_sha256=bundle.native_import.sha256)
        else:
            return None
        return binding.model_copy(update={"root":binding.root.resolve(),
            "worlds":tuple(path.resolve() for path in binding.worlds)})

    async def check_story_reuse(self, source_id: str, actor: Actor, confirmation: StoryReuseConfirmation | None = None) -> str:
        if self.story_reuse is None:
            raise ServiceError("STORY_REUSE_UNAVAILABLE","旧故事兼容检查尚未配置。",503)
        async with self.submission:
            if any(j.status in ("queued","running","awaiting_external") for j in self.jobs(actor)):
                raise ServiceError("ORGANIZER_BUSY","请等待当前制作完成。",409)
            source=self.source(source_id,actor)
            if not await asyncio.to_thread(self.review_input_ready,source_id,actor):
                raise ServiceError("REVIEW_SNAPSHOT_STALE","请先等待审核修改同步。",409)
            current=self.request(source)
            decision=None
            previous=self.story_reuse_candidate(source,actor)
            if confirmation is not None:
                pending=self.story_reuse_report(source,current)
                if (pending is None or pending.status!="needs_confirmation"
                    or CanonicalSerializer.digest(pending)!=confirmation.report_sha256
                    or pending.environment_sha256!=hashlib.sha256(current.environment.read_bytes()).hexdigest()
                    or pending.parent_story_run is None or pending.parent_draft_sha256 is None
                    or pending.parent_draft_sha256!=hashlib.sha256((pending.parent_story_run/"narrative-draft.json").read_bytes()).hexdigest()):
                    raise ServiceError("STORY_CONFIRMATION_STALE","确认对应的资料或故事已变化，请重新检查。",409)
                decision=StoryReuseDecision(actor_id=actor.actor_id,decided_at=datetime.now(UTC),
                    report_sha256=confirmation.report_sha256,environment_sha256=pending.environment_sha256,
                    parent_draft_sha256=pending.parent_draft_sha256,introduction_changes=pending.introduction_changes)
                old_lock=StoryInputLock.model_validate_json((pending.parent_story_run/"input-lock.json").read_bytes())
                previous=current.model_copy(update={"saved_story_run":pending.parent_story_run,"brief":old_lock.brief})
            output=self.store.directory / "story-reuse" / uuid4().hex
            output.mkdir(parents=True)
            empty=output/"saved-story";empty.mkdir()
            prepared=await asyncio.to_thread(self.story_reuse.prepare,
                previous,current.model_copy(update={"saved_story_run":empty}),output,decision=decision)
            pointer=output/"prepared-request.json";pointer.write_text(prepared.model_dump_json())
            identifier="reuse-"+output.name
            bound=self.bound_review_source(source,actor) if self.reviews else source
            self.store.save("native_source",identifier,RegisteredNativeSource(
                parent_source_id=source_id,owner_id=actor.actor_id,project_id=source.project_id,
                source_id=identifier,title="旧故事兼容检查 · "+source.project_id,request_file=pointer,
                review_binding_file=bound.review_binding_file))
            return identifier
