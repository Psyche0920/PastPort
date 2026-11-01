"""Compose native authoring SDK stages; source data remains separate from player code."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from pastport.adapters.environment_spatial import (
    RegisteredSpatialWorld,
    SdkEnvironmentSpatialReader,
)
from pastport.adapters.matched_environment import (
    EnvironmentRegistration,
    NativeMatchedEnvironmentReader,
)
from pastport.adapters.organizer_archives import BoundedNativeArchive, LocalResourceSnapshot
from pastport.adapters.runtime_resources import skill_root
from pastport.application.models import ServiceError
from pastport.application.source_lineage import (
    OriginalDocumentText,
    OriginalPageText,
    SourceLineageProjector,
)
from pastport.domain.capabilities import initial_capabilities
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer_inputs import NativeInputRequest, NativePreparedInputs
from pastport.domain.story_inputs import EnvironmentReadRequest, EnvironmentSnapshot
from pastport.domain.workflow import ExecutionMetadata, RemainingLimits
from pastport.ports.modules import ExecutionContext


class _Native(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _View(_Native):
    id: str
    name: str = ""


class _Tour(_Native):
    firstSceneId: str
    scenes: tuple[_View, ...]


class _HistoricalObject(_Native):
    id: int
    stable_id: str
    name: str
    historical_id: str | None
    historical_title: str | None
    historical_image: str | None
    historical_image_page: int | None
    introduction: str | None
    introduction_version: int | None
    pairing_version: int
    image_review: str
    text_review: str


class _GameData(_Native):
    objects: tuple[_HistoricalObject, ...]


@dataclass(frozen=True, slots=True)
class NativeWorldSet:
    authority: Path
    worlds: tuple[Path, ...]
    entry_scene_id: str


class _LocalCancellation:
    def __init__(self, deadline: datetime) -> None:
        self.deadline = deadline

    def raise_if_cancelled(self) -> None:
        if datetime.now(UTC) >= self.deadline:
            raise ServiceError("INPUT_READ_EXPIRED", "原生输入读取超过时限。", 408)


class NativeInputAdmission:
    def __init__(self) -> None:
        self.archives = BoundedNativeArchive()

    @staticmethod
    def tour(root: Path) -> _Tour:
        raw = BoundedNativeArchive.json(root / "vr_trial/index.html", 64 * 1024**2).decode("utf-8")
        match = re.search(
            r'<script id="tour-data" type="application/json">(.*?)</script>', raw, re.S
        )
        if match is None:
            raise ServiceError("NATIVE_TOUR_MISSING", "项目中缺少原生全景和导航数据。", 422)
        return _Tour.model_validate_json(match[1])

    def matched_vr(self, archive: Path, output: Path) -> Path:
        from pastport_matched_environment.application.vr_export import MatchedVRManifest

        if not output.exists():
            self.archives.extract(archive, output)
        manifest = MatchedVRManifest.model_validate_json(
            self.archives.json(output / "matched-vr.json")
        )
        for entry in manifest.files:
            path = (output / entry.path).resolve()
            if not path.is_relative_to(output.resolve()) or not path.is_file():
                raise ServiceError("NATIVE_RESOURCE_MISSING", "VR快照资源缺失或越界。", 422)
            if (
                path.stat().st_size != entry.size_bytes
                or self.archives.digest(path) != entry.sha256
            ):
                raise ServiceError("NATIVE_RESOURCE_CHANGED", "VR快照资源哈希不一致。", 422)
        if (
            self.archives.digest(output / "source.pdf") != manifest.source_pdf_sha256
            or self.archives.digest(output / "import-manifest.json")
            != manifest.import_manifest_sha256
        ):
            raise ServiceError("NATIVE_SOURCE_CHANGED", "VR原件或导入记录不一致。", 422)
        self.archives.database(output / "pastport_matching.sqlite3")
        self.tour(output)
        return output

    def mounted_3d(self, archive: Path, output: Path) -> NativeWorldSet:
        from pastport_matched_environment.application.scene3d_tour import TourManifest
        from pastport_matched_environment.application.shared_content import (
            CONTENT_TABLES,
            SharedContentAuthority,
        )

        if not output.exists():
            self.archives.extract(archive, output)
        manifest = TourManifest.model_validate_json(self.archives.json(output / "tour.json"))
        if (
            manifest.schema_version != "pastport.scene3d-tour/1.0"
            or len({view.source_scene_id for view in manifest.views}) != len(manifest.views)
            or manifest.entry_scene_id not in {view.source_scene_id for view in manifest.views}
        ):
            raise ServiceError("NATIVE_TOUR_INVALID", "3D导览的版本、入口或视点编号无效。", 422)
        if len(manifest.views) != 2:
            raise ServiceError(
                "GAME_HOST_VIEW_PROFILE", "当前游戏宿主需要SDK导出的双点位3D包。", 422
            )
        roots: list[Path] = []
        semantic_hash: str | None = None
        import_hash: str | None = None
        for index, view in enumerate(manifest.views, 1):
            package = (output / view.package).resolve()
            if (
                not package.is_relative_to(output.resolve())
                or self.archives.digest(package) != view.sha256
            ):
                raise ServiceError("NATIVE_WORLD_CHANGED", "3D子包哈希或路径不一致。", 422)
            root = output / "native-worlds" / str(index)
            if not root.exists():
                self.archives.extract(package, root)
                (root / "scene").rename(root / "scene3d")
                (root / "review.sqlite3").rename(root / "pastport_matching.sqlite3")
                source_tour = self.archives.json(root / "source-tour.json", 64 * 1024**2).decode()
                (root / "vr_trial").mkdir()
                (root / "vr_trial/index.html").write_text(
                    '<script id="tour-data" type="application/json">'
                    + source_tour.replace("</", "<\\/")
                    + "</script>"
                )
            attachment = json.loads(self.archives.json(root / "scene3d/attachment.json"))
            if attachment.get("source_scene_id") != view.source_scene_id:
                raise ServiceError("NATIVE_SCENE_MISMATCH", "3D子包与导览视点编号不一致。", 422)
            self.archives.database(root / "pastport_matching.sqlite3")
            current_import = self.archives.digest(root / "import-manifest.json")
            with closing(
                sqlite3.connect(
                    (root / "pastport_matching.sqlite3").as_uri() + "?mode=ro", uri=True
                )
            ) as db:
                content = tuple(
                    (
                        table,
                        tuple(sorted(db.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr)),
                    )
                    for table in CONTENT_TABLES
                )
            current_semantic = hashlib.sha256(repr(content).encode()).hexdigest()
            if semantic_hash is not None and (
                semantic_hash != current_semantic or import_hash != current_import
            ):
                raise ServiceError(
                    "NATIVE_REVIEW_DIVERGED", "两个视点的审核内容不是同一快照，不能静默合并。", 409
                )
            semantic_hash, import_hash = current_semantic, current_import
            roots.append(root)
        authority = output / "authority"
        if not authority.exists():
            shutil.copytree(roots[0], authority)
        for root in roots:
            SharedContentAuthority(root).bind(authority)
        order = {
            view.source_scene_id: root for view, root in zip(manifest.views, roots, strict=True)
        }
        ordered = (
            order[manifest.entry_scene_id],
            *(root for scene, root in order.items() if scene != manifest.entry_scene_id),
        )
        return NativeWorldSet(authority, tuple(ordered), manifest.entry_scene_id)


class NativeGameInputExporter:
    def export(
        self, request: NativeInputRequest, worlds: NativeWorldSet, original_pdf: Path, output: Path,
        *, lightweight_review: bool = False,
    ) -> GameMakingRequest:
        from pastport_evidence.adapters.assets import LocalAssetStore
        from pastport_evidence.adapters.pdf import PopplerPDFReader
        from pastport_evidence.application.pdf_ingestion import PDFIngestionService
        from pastport_evidence.domain.models import ProcessingLimits
        from pastport_evidence.domain.pdf import RegisteredPDF
        from pastport_matched_environment.api.scene3d import Scene3DStore
        from pastport_matched_environment.application.scene3d_arrows import Scene3DArrowStore
        from pastport_matched_environment.application.scene3d_export import export_scene
        from pastport_matched_environment.application.scene3d_projection import (
            OfflineCandidateProjector,
        )
        from pastport_matched_environment.application.tour_navigation import (
            Scene3DTourNavigator,
            TourDestination,
        )

        from pastport.domain.organizer_review import OrganizerReviewBinding

        output.mkdir(parents=True, exist_ok=True)
        (output / "review-binding.json").write_text(OrganizerReviewBinding(
            root=worlds.authority.resolve(), worlds=tuple(path.resolve() for path in worlds.worlds),
            import_sha256=BoundedNativeArchive.digest(worlds.authority / "import-manifest.json"),
        ).model_dump_json())
        document_file = output / "source-document.json"
        if document_file.exists():
            document = RegisteredPDF.model_validate_json(document_file.read_bytes())
            if document.source.asset.sha256 != BoundedNativeArchive.digest(original_pdf):
                raise ServiceError("ORIGINAL_SOURCE_CHANGED", "原始史料PDF已改变。", 409)
        else:
            executable = shutil.which("pdftoppm")
            if executable is None:
                raise ServiceError("PDF_READER_UNAVAILABLE", "读取原始史料需要Poppler。", 503)
            document = PDFIngestionService(
                LocalAssetStore(output / "source-assets"), PopplerPDFReader(Path(executable))
            ).register_and_extract(
                request.project_id, original_pdf, ProcessingLimits(pdf_max_bytes=512 * 1024**2)
            )
            document_file.write_text(document.model_dump_json())
        native_tour = NativeInputAdmission.tour(worlds.authority)
        by_scene = {
            json.loads((root / "scene3d/attachment.json").read_text())["source_scene_id"]: root
            for root in worlds.worlds
        }
        scene_ids = tuple(view.id for view in native_tour.scenes)
        if len(worlds.worlds) != 2 or len(by_scene) != 2 or set(by_scene) != set(scene_ids):
            raise ServiceError(
                "GAME_HOST_VIEW_PROFILE", "当前宿主要求同一导览的两个完整3D视点。", 422
            )
        # Host world indices follow the source-tour order; entry selection must not
        # swap geometry relative to scene IDs, hotspot positions or navigation.
        world_roots = tuple(by_scene[scene] for scene in scene_ids)
        navigator = Scene3DTourNavigator(
            worlds.authority,
            tuple(
                TourDestination(scene, f"http://127.0.0.1/scene3d-results/{index:032x}/")
                for index, scene in enumerate(scene_ids, 1)
            ),
        )
        for scene, root in zip(scene_ids, world_roots, strict=True):
            seed = root / "scene3d/arrow-seed.json"
            if not seed.exists():
                seed.write_text(navigator.current(scene).model_dump_json())
            OfflineCandidateProjector().initialize(root)
            OfflineCandidateProjector().initialize_arrows(root)
        native_hash = BoundedNativeArchive.digest(worlds.authority / "source.pdf")
        import_hash = BoundedNativeArchive.digest(worlds.authority / "import-manifest.json")
        environment_id = "native-" + import_hash[:24]
        source_ref = ArtifactRef(
            artifact_id="native-input-pdf",
            project_id=request.project_id,
            kind="source",
            schema_version="0.1.0",
            content_version="1",
            sha256=native_hash,
        )
        policy = request.model_copy(update={"files": ()})
        policy_ref = ArtifactRef(
            artifact_id="owned-upload-read-policy",
            project_id=request.project_id,
            kind="policy",
            schema_version="0.1.0",
            content_version="1",
            sha256=CanonicalSerializer.digest(policy),
        )
        (output / "input-read-policy.json").write_text(policy.model_dump_json())
        deadline = datetime.now(UTC) + timedelta(minutes=5)
        context = ExecutionContext(
            ExecutionMetadata(
                project_id=request.project_id,
                run_id=request.job_id,
                operation_id="native-input-read",
                execution_key=CanonicalSerializer.digest(request),
                input_refs=(source_ref,),
                policy_ref=policy_ref,
                skill_ref=None,
                model_config_ref=None,
                budget_reservation_id="local-read-no-model",
                actor_id=request.owner_id,
                deadline=deadline,
                remaining_limits=RemainingLimits(
                    model_requests=0,
                    input_tokens=0,
                    output_tokens=0,
                    search_requests=0,
                    fetch_requests=0,
                    active_seconds=300,
                    cost_microusd=0,
                ),
                allowed_tools=(),
            ),
            _LocalCancellation(deadline),
        )
        registration = EnvironmentRegistration(
            request.project_id,
            environment_id,
            worlds.authority,
            import_hash,
            native_hash,
            source_profile="large_pdf",
        )
        reader = NativeMatchedEnvironmentReader(registration)
        native = asyncio.run(
            reader.read(
                EnvironmentReadRequest(
                    project_id=request.project_id,
                    environment_id=environment_id,
                    import_manifest_sha256=import_hash,
                    source_pdf_sha256=native_hash,
                    source_ref=source_ref,
                ),
                context,
            )
        )
        projected = SourceLineageProjector().project(
            native,
            OriginalDocumentText(
                pdf_sha256=document.source.asset.sha256,
                pages=tuple(
                    OriginalPageText(page_index=p.page_index, text=p.original_text)
                    for p in document.pages
                ),
            ),
        )
        projected_snapshot = EnvironmentSnapshot.model_validate(
            projected.snapshot.model_dump() | {"entry_view_id": worlds.entry_scene_id}
        )
        (output / "native-snapshot.json").write_text(native.model_dump_json())
        (output / "source-projection.json").write_text(projected_snapshot.model_dump_json())
        spatial = SdkEnvironmentSpatialReader(
            tuple(
                RegisteredSpatialWorld(
                    root,
                    BoundedNativeArchive.digest(root / "scene3d/attachment.json"),
                    BoundedNativeArchive.digest(root / "scene3d/collider.glb"),
                )
                for root in world_roots
            ),
            worlds.authority,
            geometry_cache=output.parent / ".geometry-cache" if lightweight_review else None,
        )
        metric = spatial.read_spatial(projected_snapshot, context)
        snapshot = EnvironmentSnapshot.model_validate(
            projected_snapshot.model_dump()
            | {"metric_spatial": metric, "spatial_profile": "metric_3d_source_bound"}
        )
        environment_file = output / "environment.json"
        environment_file.write_text(snapshot.model_dump_json())
        (output / "source-lineage.json").write_text(projected.receipt.model_dump_json(indent=2))
        museum = output / "museum"
        if museum.exists():
            raise ServiceError(
                "INPUT_EXPORT_EXISTS", "输入导出已存在，需核对原交接记录后恢复。", 409
            )
        (museum / "data").mkdir(parents=True)
        resource_copy = LocalResourceSnapshot.copy if lightweight_review else shutil.copy2
        shutil.copytree(request.shared_player_assets, museum / "assets", copy_function=resource_copy)
        media = output / "media"
        media.mkdir(exist_ok=True)
        objects: list[dict[str, JsonValue]] = []
        payloads: list[dict[str, JsonValue]] = []
        for index, root in enumerate(world_roots, 1):
            archive = output / f"point-{index}.zip"
            if not archive.exists():
                export_scene(root, archive, include_assets=not lightweight_review)
            import zipfile

            with zipfile.ZipFile(archive) as bundle:
                data = _GameData.model_validate_json(bundle.read("game-data.json"))
            if index == 1:
                for item in data.objects:
                    obj = next((o for o in snapshot.objects if o.object_number == item.id), None)
                    if obj is None or obj.quote is None or item.historical_image is None:
                        continue
                    source = (root / item.historical_image).resolve()
                    if not source.is_relative_to(root.resolve()) or not source.is_file():
                        raise ServiceError("NATIVE_MEDIA_MISSING", "引用的物件资料图片缺失。", 422)
                    if source.stat().st_size > 20 * 1024**2:
                        raise ServiceError("NATIVE_MEDIA_LIMIT", "物件引用图片超过读取范围。", 422)
                    with source.open("rb") as image:
                        if image.read(8) != b"\x89PNG\r\n\x1a\n":
                            raise ServiceError("NATIVE_IMAGE_FORMAT", "原生物件图片需为PNG。", 422)
                    name = f"history-{item.id:02}.png"
                    shutil.copyfile(source, media / name)
                    target = museum / "media" / name
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(source, target)
                    objects.append(
                        {
                            "number": item.id,
                            "stable_id": item.stable_id,
                            "name": item.name,
                            "scene_ids": [
                                v.view_id
                                for v in snapshot.views
                                if any(
                                    p.object_number == item.id and p.view_id == v.view_id
                                    for p in snapshot.positions
                                )
                            ],
                            "historical_id": item.historical_id,
                            "historical_title": item.historical_title or item.name,
                            "pairing_version": item.pairing_version,
                            "image_review": item.image_review,
                            "text_review": item.text_review,
                            "image_role": "object_image",
                            "image_page": item.historical_image_page,
                            "image_source_pdf_sha256": native_hash,
                            "text_page": obj.quote.pdf_page,
                            "text_source_pdf_sha256": document.source.asset.sha256,
                            "media_path": "media/" + name,
                            "media_sha256": BoundedNativeArchive.digest(target),
                            "content_version": item.introduction_version or 0,
                            "content": item.introduction or obj.quote.text,
                            "scope_warning": obj.evidence_limitation
                            or "原生映射候选；不推断独立审核或历史复原。",
                        }
                    )
            target = museum / "worlds" / str(index)
            shutil.copytree(root / "scene3d", target / "scene3d", copy_function=resource_copy)
            trusted_assets = Path(
                str(files("pastport_matched_environment").joinpath("scene3d_assets"))
            )
            for file in trusted_assets.iterdir():
                if file.is_file():
                    shutil.copyfile(file, target / "scene3d" / file.name)
            state = TypeAdapter(dict[str, JsonValue]).validate_json(Scene3DStore(root).current())
            state["story_transitions"] = [
                dict(
                    arrow.model_dump(mode="json"),
                    targetWorld=scene_ids.index(arrow.target_scene_id) + 1,
                )
                for arrow in Scene3DArrowStore(root).current().arrows
                if arrow.target_scene_id in scene_ids
            ]
            payloads.append({"root": f"worlds/{index}", "snapshot": state})
        if not objects:
            raise ServiceError(
                "NO_SOURCE_BOUND_OBJECTS", "没有可定位到原始史料的物件引用；未调用Story模型。", 422
            )
        caps = initial_capabilities().model_dump(mode="json")
        presentation: dict[str, JsonValue] = {
            "objects": [obj for obj in objects],
            "tourId": environment_id,
            "shots": [],
            "panoramaHashes": {view.view_id: view.panorama_sha256 for view in snapshot.views},
            "scenes": [
                {
                    "id": view.view_id,
                    "name": f"点位 {index}",
                    "hotspots": [
                        {"number": p.object_number, "yaw": p.yaw, "pitch": p.pitch}
                        for p in snapshot.positions
                        if p.view_id == view.view_id
                    ],
                }
                for index, view in enumerate(snapshot.views, 1)
            ],
            "walkArea": None,
            "sourceNotes": {
                str(obj.object_number): obj.evidence_limitation or "候选映射，独立审核状态保留。"
                for obj in snapshot.objects
            },
            "runtimeCapabilities": caps,
            "spatialContext": {
                "schema_version": "story-spatial-context-0.1.0",
                "input_sha256": BoundedNativeArchive.digest(environment_file),
                "metric_revision": metric.revision,
                "worlds": metric.model_dump(mode="json")["worlds"],
            },
        }
        (museum / "data/presentation.json").write_text(json.dumps(presentation, ensure_ascii=False))
        (museum / "data/runtime.json").write_text(json.dumps({"runtime_compatibility": caps}))
        (museum / "data/scene3d-input.json").write_text(json.dumps({"worlds": payloads}))
        empty = output / "no-saved-story"
        empty.mkdir(exist_ok=True)
        return GameMakingRequest(
            original_pdf=original_pdf,
            source_document=document_file,
            environment=environment_file,
            media_directory=media,
            museum_directory=museum,
            saved_story_run=empty,
            skills_directory=skill_root(),
            brief=request.options.brief,
            output_directory=output.parent,
        )


class SDKUploadedInputPreparer:
    def __init__(self) -> None:
        from pastport.adapters.organizer_processes import NativeSDKProcessRunner

        self.runner = NativeSDKProcessRunner()
        self.admission = NativeInputAdmission()

    def close(self) -> None:
        self.runner.close()

    @staticmethod
    def _record(output: Path, stage: str, artifact: Path) -> None:
        directory = output / "native-receipts"
        directory.mkdir(exist_ok=True)
        (directory / (stage + ".json")).write_text(
            json.dumps(
                {
                    "stage": stage,
                    "artifact": str(artifact),
                    "sha256": BoundedNativeArchive.digest(artifact),
                }
            )
        )

    @staticmethod
    def _stages(output: Path) -> tuple[str, ...]:
        order = ("evidence", "matched_environment", "scene3d_1", "scene3d_2", "input_handoff")
        return tuple(
            stage for stage in order if (output / "native-receipts" / (stage + ".json")).is_file()
        )

    @staticmethod
    def _one(request: NativeInputRequest, role: str) -> Path | None:
        files = tuple(file for file in request.files if file.role == role)
        if len(files) > 1:
            raise ServiceError(
                "MATERIAL_ROLE_AMBIGUOUS", "同一单文件材料栏有多个文件，请先移除旧文件。", 422
            )
        return files[0].path if files else None

    @staticmethod
    def _copy_inputs(request: NativeInputRequest, output: Path) -> Path:
        inputs = output / "admitted-inputs"
        inputs.mkdir(exist_ok=True)
        for asset in request.files:
            if (
                asset.path.is_symlink()
                or not asset.path.is_file()
                or BoundedNativeArchive.digest(asset.path) != asset.sha256
            ):
                raise ServiceError("UPLOADED_INPUT_CHANGED", "上传材料已改变或缺失。", 409)
            suffix = Path(asset.filename).suffix.lower()
            if asset.role == "photos" and suffix not in (".jpg", ".jpeg", ".png", ".webp"):
                raise ServiceError("PHOTO_FORMAT_UNSUPPORTED", "现场照片需为JPEG、PNG或WebP。", 422)
            if suffix not in (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".html", ".zip"):
                raise ServiceError("MATERIAL_FORMAT_UNSUPPORTED", "材料格式不受当前入口支持。", 422)
            target = inputs / (asset.file_id + suffix)
            if target.exists():
                if BoundedNativeArchive.digest(target) != asset.sha256:
                    raise ServiceError("ADMITTED_INPUT_CHANGED", "保存的输入快照已改变。", 409)
            else:
                shutil.copyfile(asset.path, target)
        return inputs

    @staticmethod
    def _path(request: NativeInputRequest, inputs: Path, role: str) -> Path | None:
        values = tuple(asset for asset in request.files if asset.role == role)
        if len(values) > 1:
            raise ServiceError("MATERIAL_ROLE_AMBIGUOUS", "单文件材料栏只能有一个有效文件。", 422)
        return (
            inputs / (values[0].file_id + Path(values[0].filename).suffix.lower())
            if values
            else None
        )

    def _tour_preflight(self, request: NativeInputRequest, tour: Path, output: Path) -> Path:
        from pastport_matched_environment.adapters.assets import LocalAssetStore
        from pastport_matched_environment.adapters.tour import TourImporter
        from pastport_matched_environment.application.environment_agent import offline_input_limits
        from pastport_matched_environment.application.studio import prepare_tour

        folder = output / "tour-input"
        if tour.suffix == ".zip":
            if not folder.exists():
                self.admission.archives.extract(tour, folder)
        else:
            folder.mkdir(exist_ok=True)
            if not (folder / "index.html").exists():
                shutil.copyfile(tour, folder / "index.html")
        prepared = prepare_tour(folder)
        store = LocalAssetStore(output / "tour-preflight-assets")
        imported = TourImporter(store).import_html(
            request.project_id, prepared, offline_input_limits(large_pdf=True)
        )
        if len(imported.views) != 2:
            raise ServiceError("GAME_HOST_VIEW_PROFILE", "当前成品宿主需要两个视点的360导览。", 422)
        if any(
            store.resolve_path(view.panorama).stat().st_size > 10 * 1024**2
            for view in imported.views
        ):
            raise ServiceError(
                "MARBLE_PANORAMA_LIMIT", "每个360视点须符合3D服务的10MiB输入范围。", 422
            )
        return prepared

    def prepare(self, request: NativeInputRequest, output: Path) -> NativePreparedInputs:
        from pastport_evidence.application.document_package import OutputPaths
        from pastport_evidence.domain.execution import SubscriptionGrant as EvidenceGrant
        from pastport_matched_environment.domain.environment import RunResultPointer
        from pastport_matched_environment.domain.execution import (
            SubscriptionGrant as EnvironmentGrant,
        )

        output.mkdir(parents=True, exist_ok=True)
        if not request.options.authorize_model:
            raise ServiceError(
                "MODEL_AUTHORIZATION_REQUIRED", "新材料制作需要确认本次生成调用。", 422
            )
        if request.shared_player_assets.is_symlink() or not request.shared_player_assets.is_dir():
            raise ServiceError("PLAYER_ASSETS_UNAVAILABLE", "服务器尚未配置共享播放器资源。", 503)
        assets = tuple(request.shared_player_assets.rglob("*"))
        if (
            any(path.is_symlink() for path in assets)
            or sum(path.stat().st_size for path in assets if path.is_file()) > 200 * 1024**2
        ):
            raise ServiceError(
                "PLAYER_ASSETS_INVALID", "共享播放器资源超过配置范围或包含链接。", 503
            )
        inputs = self._copy_inputs(request, output)
        prepared_file = output / "prepared-request.json"
        if prepared_file.is_file():
            return NativePreparedInputs(
                state="ready",
                request=GameMakingRequest.model_validate_json(prepared_file.read_bytes()),
                completed_stages=self._stages(output),
                message="已复用原生输入交接结果。",
            )
        original = self._path(request, inputs, "original_pdf")
        if original is None:
            raise ServiceError("ORIGINAL_PDF_REQUIRED", "缺少原始史料PDF。", 422)
        tour_input = self._path(request, inputs, "tour")
        tour = self._tour_preflight(request, tour_input, output) if tour_input else None
        if request.entry_level == "3d":
            archive = self._path(request, inputs, "mounted_3d")
            if archive is None or archive.suffix != ".zip":
                raise ServiceError(
                    "MOUNTED_TOUR_REQUIRED", "请上传环境SDK导出的双点位3D ZIP。", 422
                )
            worlds = self.admission.mounted_3d(archive, output / "mounted-3d")
        else:
            expected = {"marble-1.1": 1500, "marble-1.0-draft": 150}[request.options.marble_model]
            if (request.entry_level != "raw" or tour is not None) and (
                not request.options.authorize_marble
                or request.options.marble_credit_budget < expected
            ):
                raise ServiceError(
                    "MARBLE_AUTHORIZATION_REQUIRED", "需要确认两个视点的3D生成及每点授权预算。", 422
                )
            if (request.entry_level != "raw" or tour is not None) and not os.environ.get(
                "WORLDLABS_API_KEY"
            ):
                raise ServiceError(
                    "MARBLE_NOT_CONFIGURED", "3D生成服务尚未配置；材料已保存，未发起生成。", 503
                )
            if request.entry_level == "vr":
                archive = self._path(request, inputs, "matched_vr")
                if archive is None or archive.suffix != ".zip":
                    raise ServiceError(
                        "MATCHED_VR_REQUIRED", "请上传环境SDK导出的匹配VR ZIP。", 422
                    )
                environment = self.admission.matched_vr(archive, output / "matched-vr")
            else:
                mapping = self._path(request, inputs, "mapping_pdf")
                if request.entry_level == "raw":
                    photos = tuple(asset for asset in request.files if asset.role == "photos")
                    if not 1 <= len(photos) <= 100:
                        raise ServiceError(
                            "PHOTOS_REQUIRED", "原始材料起点需要1至100张现场照片。", 422
                        )
                    folder = output / "photos"
                    folder.mkdir(exist_ok=True)
                    for asset in photos:
                        suffix = Path(asset.filename).suffix.lower()
                        target = folder / (asset.file_id + suffix)
                        if not target.exists():
                            shutil.copyfile(inputs / target.name, target)
                    workspace = output / "evidence"
                    result_file = workspace / "result.json"
                    if not result_file.exists():
                        grant = EvidenceGrant(
                            grant_ref="org_" + request.job_id + "_evidence",
                            project_id=request.project_id,
                            max_calls=request.options.max_evidence_calls,
                            max_recorded_tokens=request.options.max_recorded_tokens,
                            timeout_seconds=240,
                        )
                        grant_file = output / "evidence-grant.json"
                        if not grant_file.exists():
                            grant_file.write_text(grant.model_dump_json())
                        self.runner.run(
                            "pastport_evidence.cli",
                            (
                                "--pdf",
                                str(original),
                                "--photos",
                                str(folder),
                                "--workspace",
                                str(workspace),
                                "--grant",
                                str(grant_file),
                                "--run-id",
                                request.job_id,
                                "--large-pdf",
                            ),
                            240 * request.options.max_evidence_calls + 120,
                        )
                    documents = OutputPaths.model_validate_json(result_file.read_bytes())
                    mapping = Path(documents.pdf).resolve()
                    if not mapping.is_relative_to(workspace.resolve()):
                        raise ServiceError(
                            "MAPPING_OUTPUT_SCOPE", "映射PDF输出不在本次工作区内。", 409
                        )
                    self._record(output, "evidence", mapping)
                    if tour is None:
                        return NativePreparedInputs(
                            state="awaiting_materials",
                            mapping_pdf=mapping,
                            completed_stages=self._stages(output),
                            message="映射PDF已生成并保存；补充360导览后从此处继续。",
                        )
                if mapping is None or tour is None:
                    raise ServiceError(
                        "MAPPING_AND_TOUR_REQUIRED", "此起点需要映射PDF和360导览。", 422
                    )
                workspace = output / "environment-build"
                pointer_file = workspace / "runs" / request.job_id / "result-pointer.json"
                if not pointer_file.exists():
                    environment_grant = EnvironmentGrant(
                        grant_ref="org_" + request.job_id + "_environment",
                        project_id=request.project_id,
                        max_calls=request.options.max_environment_calls,
                        max_recorded_tokens=request.options.max_recorded_tokens,
                        timeout_seconds=240,
                    )
                    grant_file = output / "environment-grant.json"
                    if not grant_file.exists():
                        grant_file.write_text(environment_grant.model_dump_json())
                    self.runner.run(
                        "pastport_matched_environment.cli",
                        (
                            "environment-build",
                            "--pdf",
                            str(mapping),
                            "--tour",
                            str(tour),
                            "--grant",
                            str(grant_file),
                            "--workspace",
                            str(workspace),
                            "--run-id",
                            request.job_id,
                            "--large-pdf",
                        ),
                        240 * request.options.max_environment_calls + 120,
                    )
                pointer = RunResultPointer.model_validate_json(pointer_file.read_bytes())
                environment = workspace / "runs" / pointer.result_run_id / "result"
            self._record(output, "matched_environment", environment / "import-manifest.json")
            imported = self.admission.tour(environment)
            if len(imported.scenes) != 2:
                raise ServiceError("GAME_HOST_VIEW_PROFILE", "当前游戏宿主需要两个原生视点。", 422)
            roots = []
            for index, view in enumerate(imported.scenes, 1):
                workspace = output / f"scene3d-{index}"
                delivery = workspace / "attachment/delivery.json"
                if not delivery.exists():
                    self.runner.run(
                        "pastport_matched_environment.cli",
                        (
                            "scene3d-generate",
                            "--environment",
                            str(environment),
                            "--workspace",
                            str(workspace),
                            "--source-scene",
                            view.id,
                            "--model",
                            request.options.marble_model,
                            "--credit-budget",
                            str(request.options.marble_credit_budget),
                            "--authorize-marble",
                        ),
                        240,
                    )
                if not delivery.exists():
                    return NativePreparedInputs(
                        state="awaiting_external",
                        completed_stages=self._stages(output),
                        message=f"3D视点{index}已提交，等待同一服务操作返回；不会重新提交。",
                    )
                roots.append(workspace / "attachment/result")
                self._record(output, f"scene3d_{index}", delivery)
            worlds = NativeWorldSet(environment, tuple(roots), imported.firstSceneId)
        final = output / "handoff"
        if final.exists():
            prepared = GameMakingRequest.model_validate_json((final / "request.json").read_bytes())
            pending = prepared.source_document.parent
            if pending.parent != output or not pending.name.startswith("handoff.pending-"):
                raise ServiceError("HANDOFF_RECOVERY_SCOPE", "原交接记录的来源范围无效。", 409)
        else:
            # Fresh attempt directory: preserve all existing partial and accepted outputs.
            pending = output / ("handoff.pending-" + uuid4().hex)
            prepared = NativeGameInputExporter().export(request, worlds, original, pending)
            (pending / "request.json").write_text(prepared.model_dump_json())
            pending.rename(final)
        prepared = prepared.model_copy(
            update={
                name: final / value.relative_to(pending)
                for name, value in prepared
                if isinstance(value, Path) and value.is_relative_to(pending)
            }
        )
        prepared_file.write_text(prepared.model_dump_json(indent=2))
        self._record(output, "input_handoff", prepared_file)
        return NativePreparedInputs(
            state="ready",
            request=prepared,
            completed_stages=self._stages(output),
            message="原始资料、审核与3D空间已交接，可继续Story生成。",
        )

    def model_calls(self, output: Path) -> int | None:
        count = 0
        for stage in ("evidence", "environment-build"):
            path = output / stage / "codex-executions.sqlite3"
            if not path.exists():
                continue
            try:
                with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                    rows = db.execute("SELECT state,result FROM executions").fetchall()
                if any(state != "completed" or result is None for state, result in rows):
                    return None
                count += len(rows)
            except sqlite3.Error:
                return None
        return count
