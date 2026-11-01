"""Validate one registered cache lineage; never assemble unrelated saved results."""

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer, Contract, Sha256
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.story_inputs import EnvironmentSnapshot


class CachedFile(Contract):
    path: Path
    sha256: Sha256


class CachedWorld(Contract):
    attachment: CachedFile
    collider: CachedFile
    splat: CachedFile
    source_panorama: CachedFile


class OrganizerCachedBundle(Contract):
    schema_version: str = "pastport.organizer-cache/1.0"
    request_sha256: Sha256
    original_pdf: CachedFile
    photo_manifest: CachedFile
    photos: tuple[CachedFile, ...] = Field(min_length=1, max_length=100)
    mapping_pdf: CachedFile
    objects: CachedFile
    tour: CachedFile
    native_import: CachedFile
    worlds: tuple[CachedWorld, ...] = Field(min_length=2, max_length=2)


class _Native(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _Source(_Native):
    sha256: Sha256
    pages: int


class _Photo(_Native):
    sha256: Sha256


class _PhotoManifest(_Native):
    source: _Source
    photos: tuple[_Photo, ...]


class _Import(_Native):
    source_pdf_sha256: Sha256
    input_pdf_sha256: Sha256
    input_vr_sha256: Sha256
    upstream_objects_sha256: Sha256


class _Attachment(_Native):
    source_scene_id: str
    source_import_sha256: Sha256


class _Document(_Native):
    page_count: int


class CachedBundleValidator:
    @staticmethod
    def _verify(file: CachedFile) -> None:
        if (
            file.path.is_symlink()
            or not file.path.is_file()
            or file.path.stat().st_size > 512 * 1024**2
        ):
            raise ServiceError("CACHE_FILE_UNAVAILABLE", "整套缓存的文件缺失或超过读取范围。", 409)
        with file.path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != file.sha256:
            raise ServiceError("CACHE_FILE_CHANGED", "整套缓存有文件改变，不能混用其它版本。", 409)

    @classmethod
    def validate(cls, path: Path, request: GameMakingRequest) -> OrganizerCachedBundle:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024**2:
            raise ServiceError("CACHE_BUNDLE_INVALID", "整套缓存登记文件无效。", 409)
        bundle = OrganizerCachedBundle.model_validate_json(path.read_bytes())
        if (
            bundle.schema_version != "pastport.organizer-cache/1.0"
            or bundle.request_sha256 != CanonicalSerializer.digest(request)
        ):
            raise ServiceError("CACHE_REQUEST_CHANGED", "缓存登记与制作输入不是同一版本。", 409)
        references = (
            bundle.original_pdf,
            bundle.photo_manifest,
            *bundle.photos,
            bundle.mapping_pdf,
            bundle.objects,
            bundle.tour,
            bundle.native_import,
            *(
                file
                for world in bundle.worlds
                for file in (world.attachment, world.collider, world.splat, world.source_panorama)
            ),
        )
        for file in references:
            cls._verify(file)
        if bundle.original_pdf.path.resolve() != request.original_pdf.resolve():
            raise ServiceError("CACHE_SOURCE_CHANGED", "缓存原件不是本次选择的史料。", 409)
        if any(
            not (request.saved_story_run / name).is_file()
            for name in (
                "input-lock.json",
                "narrative-draft.json",
                "story-check.json",
                "budget.json",
            )
        ):
            raise ServiceError(
                "CACHE_STORY_INCOMPLETE", "完整资料集缺少已保存故事，默认复用已停止。", 409
            )
        photos = _PhotoManifest.model_validate_json(bundle.photo_manifest.path.read_bytes())
        native = _Import.model_validate_json(bundle.native_import.path.read_bytes())
        snapshot = EnvironmentSnapshot.model_validate_json(request.environment.read_bytes())
        document = _Document.model_validate_json(request.source_document.read_bytes())
        if (
            photos.source.sha256 != bundle.original_pdf.sha256
            or photos.source.pages != document.page_count
            or native.source_pdf_sha256 != bundle.original_pdf.sha256
            or native.input_pdf_sha256 != bundle.mapping_pdf.sha256
            or native.input_vr_sha256 != bundle.tour.sha256
            or native.upstream_objects_sha256 != bundle.objects.sha256
            or snapshot.import_manifest_sha256 != bundle.native_import.sha256
            or snapshot.source_pdf_sha256 != bundle.original_pdf.sha256
        ):
            raise ServiceError(
                "CACHE_LINEAGE_MISMATCH", "照片、映射、VR和史料不属于同一套缓存。", 409
            )
        if len(photos.photos) != len(bundle.photos) or {p.sha256 for p in photos.photos} != {
            p.sha256 for p in bundle.photos
        }:
            raise ServiceError("CACHE_PHOTOS_MISMATCH", "缓存照片清单与所选照片不一致。", 409)
        scene_ids = set()
        views = {view.view_id: view for view in snapshot.views}
        for world in bundle.worlds:
            attachment = _Attachment.model_validate_json(world.attachment.path.read_bytes())
            if (
                attachment.source_scene_id not in views
                or attachment.source_import_sha256 != bundle.native_import.sha256
                or world.source_panorama.sha256 != views[attachment.source_scene_id].panorama_sha256
            ):
                raise ServiceError(
                    "CACHE_WORLD_MISMATCH", "已有3D场景不是这套VR及其视点的产物。", 409
                )
            scene_ids.add(attachment.source_scene_id)
        if scene_ids != set(views):
            raise ServiceError("CACHE_WORLD_MISSING", "整套缓存缺少对应的3D点位。", 409)
        return bundle
