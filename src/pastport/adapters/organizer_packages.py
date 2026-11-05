"""Shared delivery packages: immutable versions, an explicit current pointer, resumable upload."""

import hashlib
import re
import secrets
import shutil
import tarfile
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from pastport.adapters.organizer_delivery import MAX_BYTES, delivery_name, import_delivery
from pastport.application.models import Actor, ServiceError
from pastport.domain.common import Contract, Identifier, Sha256
from pastport.domain.organizer import OrganizerJob
from pastport.ports.organizer import OrganizerRepository

ARCHIVE_NAME = "delivery.tar.gz"
CHUNK_BYTES = 16 * 1024**2  # Below common tunnel request limits (Cloudflare: 100 MB).
MAXIMUM_CHUNK = 32 * 1024**2
UPLOAD_LIFETIME = 6 * 3600


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DeliveryVersion(Contract):
    job_id: Identifier
    number: int = Field(ge=1)
    parent_job_id: Identifier | None = None
    archive_sha256: Sha256
    size_bytes: int = Field(ge=0)
    submitted_at: str
    note: str = Field(default="", max_length=500)


class DeliveryEvent(Contract):
    kind: Literal["submitted", "restored", "registered"]
    job_id: Identifier
    at: str


class DeliveryPackage(Contract):
    package_id: Identifier
    owner_id: Identifier
    name: Identifier
    revision: int = Field(ge=1)
    current_job_id: Identifier
    versions: tuple[DeliveryVersion, ...]
    events: tuple[DeliveryEvent, ...] = ()


class DeliverySubmission(Contract):
    base_job_id: Identifier | None = None
    note: str = Field(default="", max_length=500)


class DeliveryRestore(Contract):
    job_id: Identifier
    expected_revision: int = Field(ge=1)


class DeliveryUploadStart(Contract):
    filename: str = Field(min_length=1, max_length=120)
    size: int = Field(gt=0, le=MAX_BYTES)


class DeliveryUploadState(Contract):
    upload_id: Identifier
    received: int = Field(ge=0)
    size: int = Field(gt=0)
    chunk_bytes: int = Field(gt=0)


class DeliveryResult(Contract):
    job: OrganizerJob
    package: DeliveryPackage
    created: bool


class DeliveryMaterial(Contract):
    label: str
    available: bool
    href: str | None = None
    detail: str = ""


def is_delivery(job: OrganizerJob, store: OrganizerRepository) -> bool:
    """Imported snapshots use their own id as source and have no production request."""
    root = store.directory / "jobs" / job.job_id
    return (
        job.source_id == job.job_id
        and job.input_kind == "registered"
        and (root / "game-3d").is_dir()
        and not (root / "organizer-production-request.json").exists()
    )


class DeliveryLibrary:
    """One shared history: a new version never replaces another; the pointer moves only by CAS."""

    def __init__(self, store: OrganizerRepository) -> None:
        self.store = store
        self.lock = threading.RLock()

    @staticmethod
    def package_id(owner_id: str, name: str) -> str:
        return hashlib.sha256(f"package\0{owner_id}\0{name}".encode()).hexdigest()[:32]

    def packages(self, actor: Actor) -> tuple[DeliveryPackage, ...]:
        with self.lock:
            self._register_legacy(actor.actor_id)
            values = [
                package
                for package in self.store.list("package", DeliveryPackage)
                if package.owner_id == actor.actor_id
                and (actor.project_ids is None or package.name in actor.project_ids)
            ]
        return tuple(sorted(values, key=lambda package: package.name))

    def package(self, actor: Actor, package_id: str) -> DeliveryPackage:
        package = self.store.get("package", package_id, DeliveryPackage)
        if package.owner_id != actor.actor_id or (
            actor.project_ids is not None and package.name not in actor.project_ids
        ):
            raise ServiceError("DELIVERY_FORBIDDEN", "没有此游戏包的权限。", 403)
        return package

    def _find(self, owner_id: str, name: str) -> DeliveryPackage | None:
        try:
            return self.store.get("package", self.package_id(owner_id, name), DeliveryPackage)
        except ServiceError as error:
            if error.code == "ORGANIZER_NOT_FOUND":
                return None
            raise

    def _register_legacy(self, owner_id: str) -> None:
        """Group imports made before versioning, oldest first; the newest stays current."""
        groups: dict[str, list[OrganizerJob]] = {}
        for job in reversed(self.store.list("job", OrganizerJob)):
            if job.owner_id == owner_id and is_delivery(job, self.store):
                groups.setdefault(job.project_id, []).append(job)
        for name, jobs in groups.items():
            package = self._find(owner_id, name)
            known = {version.job_id for version in package.versions} if package else set()
            missing = [job for job in jobs if job.job_id not in known]
            if not missing:
                continue
            versions = list(package.versions) if package else []
            events = list(package.events) if package else []
            for job in missing:
                parent = versions[-1].job_id if versions else None
                versions.append(
                    DeliveryVersion(
                        job_id=job.job_id,
                        number=len(versions) + 1,
                        parent_job_id=parent,
                        archive_sha256=job.input_sha256,
                        size_bytes=self._archive_size(job),
                        submitted_at=self._job_time(job),
                        note="导入记录（版本管理启用前）",
                    )
                )
                events.append(DeliveryEvent(kind="registered", job_id=job.job_id, at=now()))
            current = package.current_job_id if package else versions[-1].job_id
            self.store.save(
                "package",
                self.package_id(owner_id, name),
                DeliveryPackage(
                    package_id=self.package_id(owner_id, name),
                    owner_id=owner_id,
                    name=name,
                    revision=(package.revision + 1) if package else 1,
                    current_job_id=current,
                    versions=tuple(versions),
                    events=tuple(events),
                ),
            )

    def _archive_size(self, job: OrganizerJob) -> int:
        archive = self.store.directory / "jobs" / job.job_id / ARCHIVE_NAME
        return archive.stat().st_size if archive.is_file() else 0

    def _job_time(self, job: OrganizerJob) -> str:
        root = self.store.directory / "jobs" / job.job_id
        stamp = root.stat().st_mtime if root.exists() else time.time()
        return datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds")

    def submit(
        self, actor: Actor, name: str, archive: Path, submission: DeliverySubmission
    ) -> DeliveryResult:
        """Import a new immutable version; refuse when the base is no longer current."""
        with self.lock:
            self._register_legacy(actor.actor_id)
            package = self._find(actor.actor_id, name)
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            key = hashlib.sha256(f"{actor.actor_id}\0{name}\0{digest}".encode()).hexdigest()[:32]
            if package is not None:
                existing = next((v for v in package.versions if v.job_id == key), None)
                if existing is not None:
                    # A retried or repeated upload of identical bytes changes nothing.
                    job = self.store.get("job", key, OrganizerJob)
                    return DeliveryResult(job=job, package=package, created=False)
                current = next(v for v in package.versions if v.job_id == package.current_job_id)
                if submission.base_job_id is None:
                    raise ServiceError(
                        "DELIVERY_NAME_EXISTS",
                        f"已有同名游戏包 {name}（当前第 {current.number} 版）。"
                        "请在它的卡片上用「提交新版」，以免与他人的版本混淆。",
                        409,
                    )
                if submission.base_job_id != package.current_job_id:
                    raise ServiceError(
                        "DELIVERY_VERSION_CONFLICT",
                        f"{name} 已有更新的第 {current.number} 版（{current.submitted_at}）。"
                        "你的文件未保存；请先下载最新版并合并修改后再提交。",
                        409,
                    )
            elif submission.base_job_id is not None:
                raise ServiceError("DELIVERY_BASE_UNKNOWN", "找不到要更新的原版本。", 409)
            job = import_delivery(self.store, actor.actor_id, name, archive)
            stored = self.store.directory / "jobs" / job.job_id / ARCHIVE_NAME
            if not stored.is_file():
                partial = stored.with_name(".delivery-copy")
                shutil.copyfile(archive, partial)
                partial.replace(stored)
            version = DeliveryVersion(
                job_id=job.job_id,
                number=(max(v.number for v in package.versions) + 1) if package else 1,
                parent_job_id=package.current_job_id if package else None,
                archive_sha256=digest,
                size_bytes=stored.stat().st_size,
                submitted_at=now(),
                note=submission.note.strip(),
            )
            updated = DeliveryPackage(
                package_id=self.package_id(actor.actor_id, name),
                owner_id=actor.actor_id,
                name=name,
                revision=(package.revision + 1) if package else 1,
                current_job_id=job.job_id,
                versions=(*(package.versions if package else ()), version),
                events=(
                    *(package.events if package else ()),
                    DeliveryEvent(kind="submitted", job_id=job.job_id, at=version.submitted_at),
                ),
            )
            self.store.save("package", updated.package_id, updated)
            return DeliveryResult(job=job, package=updated, created=True)

    def restore(self, actor: Actor, package_id: str, request: DeliveryRestore) -> DeliveryPackage:
        with self.lock:
            package = self.package(actor, package_id)
            if request.expected_revision != package.revision:
                raise ServiceError(
                    "DELIVERY_VERSION_CONFLICT",
                    "此游戏包刚被他人更新，请查看最新列表后再操作。",
                    409,
                )
            if not any(version.job_id == request.job_id for version in package.versions):
                raise ServiceError("DELIVERY_VERSION_UNKNOWN", "此版本不属于该游戏包。", 404)
            updated = package.model_copy(
                update={
                    "revision": package.revision + 1,
                    "current_job_id": request.job_id,
                    "events": (
                        *package.events,
                        DeliveryEvent(kind="restored", job_id=request.job_id, at=now()),
                    ),
                }
            )
            self.store.save("package", package_id, updated)
            return updated

    def archive(self, job: OrganizerJob, game: Path) -> Path:
        """The submitted archive, or a re-importable archive built once from the game files."""
        root = self.store.directory / "jobs" / job.job_id
        stored = root / ARCHIVE_NAME
        if stored.is_file():
            return stored
        if not game.is_dir():
            raise ServiceError("DELIVERY_UNAVAILABLE", "此记录没有可下载的游戏文件。", 404)
        partial = root / ".delivery-build"
        with self.lock:
            if stored.is_file():
                return stored
            try:
                with tarfile.open(partial, "w:gz") as package:
                    package.add(game, arcname=download_name(job.project_id), filter=_regular)
                partial.replace(stored)
            finally:
                partial.unlink(missing_ok=True)
        return stored

    def materials(self, job: OrganizerJob, game: Path) -> tuple[DeliveryMaterial, ...]:
        base = f"/organizer/api/jobs/{job.job_id}"
        items = [
            DeliveryMaterial(
                label="游戏包（可重新导入的 .tar.gz）",
                available=True,
                href=base + "/download",
                detail=download_name(job.project_id) + ".tar.gz",
            )
        ]
        editable = sorted(
            path.relative_to(game).as_posix()
            for path in game.rglob("*")
            if path.is_file()
            and (
                path.relative_to(game).parts[0] in ("authoring",)
                or path.name in ("MANIFEST.md", "delivery-provenance.json", "base-story.json")
                or path.name.startswith("blueprint")
            )
        )[:60]
        items.append(
            DeliveryMaterial(
                label="包内可编辑源文件",
                available=bool(editable),
                detail="、".join(editable)
                if editable
                else "包内未附源文件；只能直接修改游戏文件后提交新版",
            )
        )
        receipt = self.store.directory / "jobs" / job.job_id / "native-result.json"
        if job.input_kind == "uploads":
            items.append(
                DeliveryMaterial(
                    label="上传的原始材料",
                    available=True,
                    href=f"/organizer/api/materials/{job.project_id}",
                    detail="见项目材料清单",
                )
            )
            items.append(
                DeliveryMaterial(
                    label="匹配结果（映射 PDF）",
                    available=receipt.is_file(),
                    href=base + "/mapping.pdf" if receipt.is_file() else None,
                    detail="" if receipt.is_file() else "后台没有此记录的映射文档",
                )
            )
        else:
            for label in ("原始史料与现场照片", "匹配结果"):
                items.append(
                    DeliveryMaterial(
                        label=label, available=False, detail="交付包导入时未附带，后台没有保存"
                    )
                )
        return tuple(items)


def download_name(project_id: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", project_id).strip("-_")[:80] or "delivery"
    return name if name[0].isalnum() else "d" + name[:79]


def _regular(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    return member if member.isfile() or member.isdir() else None


@dataclass(slots=True)
class _Upload:
    owner_id: str
    filename: str
    size: int
    path: Path
    created: float
    received: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class ChunkedUploads:
    """Resumable, ordered chunks; a repeated chunk is acknowledged, a gap is refused."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        shutil.rmtree(directory, ignore_errors=True)  # Incomplete uploads never survive restart.
        directory.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, _Upload] = {}
        self.lock = threading.Lock()

    def _expire(self) -> None:
        deadline = time.monotonic() - UPLOAD_LIFETIME
        for key, upload in list(self.sessions.items()):
            if upload.created < deadline:
                self.discard(key)

    def start(self, owner_id: str, request: DeliveryUploadStart) -> DeliveryUploadState:
        delivery_name(request.filename)
        with self.lock:
            self._expire()
            if sum(1 for u in self.sessions.values() if u.owner_id == owner_id) >= 4:
                raise ServiceError("DELIVERY_UPLOAD_LIMIT", "同时进行的上传过多，请稍后再试。", 429)
            key = secrets.token_hex(16)
            path = self.directory / key
            path.touch(mode=0o600, exist_ok=False)
            self.sessions[key] = _Upload(
                owner_id, request.filename, request.size, path, time.monotonic()
            )
        return DeliveryUploadState(
            upload_id=key, received=0, size=request.size, chunk_bytes=CHUNK_BYTES
        )

    def _session(self, owner_id: str, key: str) -> _Upload:
        upload = self.sessions.get(key)
        if upload is None or upload.owner_id != owner_id:
            raise ServiceError(
                "DELIVERY_UPLOAD_UNKNOWN", "上传会话已失效（服务可能已重启），请重新上传。", 404
            )
        return upload

    async def append(
        self, owner_id: str, key: str, offset: int, chunks: AsyncIterator[bytes]
    ) -> DeliveryUploadState:
        upload = self._session(owner_id, key)
        if not upload.lock.acquire(blocking=False):
            raise ServiceError("DELIVERY_UPLOAD_BUSY", "此分块正在上传，请稍候。", 409)
        try:
            if offset > upload.received or offset < 0:
                raise ServiceError("DELIVERY_UPLOAD_GAP", "上传分块顺序不符，请从断点继续。", 409)
            position, size = offset, 0
            with upload.path.open("r+b") as stream:
                stream.seek(offset)
                async for chunk in chunks:
                    size += len(chunk)
                    if size > MAXIMUM_CHUNK or offset + size > upload.size:
                        raise ServiceError("DELIVERY_UPLOAD_LIMIT", "上传分块超出声明大小。", 413)
                    # Bytes before `received` were already confirmed: skip, never rewrite.
                    skip = max(0, min(len(chunk), upload.received - position))
                    if skip < len(chunk):
                        stream.seek(position + skip)
                        stream.write(chunk[skip:])
                    position += len(chunk)
            upload.received = max(upload.received, position)
        finally:
            upload.lock.release()
        return DeliveryUploadState(
            upload_id=key, received=upload.received, size=upload.size, chunk_bytes=CHUNK_BYTES
        )

    def complete(self, owner_id: str, key: str) -> tuple[str, Path]:
        upload = self._session(owner_id, key)
        if upload.received != upload.size or upload.path.stat().st_size != upload.size:
            raise ServiceError("DELIVERY_UPLOAD_INCOMPLETE", "文件尚未完整上传。", 409)
        return upload.filename, upload.path

    def discard(self, key: str) -> None:
        upload = self.sessions.pop(key, None)
        if upload is not None:
            upload.path.unlink(missing_ok=True)
