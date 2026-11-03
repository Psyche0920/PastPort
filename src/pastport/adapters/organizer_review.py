"""Translate registered native review records without copying their authority."""
import hashlib
import json
from html import escape
from typing import Literal
from importlib.resources import files
from urllib.parse import urlsplit
import shutil
import sqlite3
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from pastport.adapters.organizer_archives import BoundedNativeArchive
from pastport.application.models import ServiceError
from pastport.application.organizer_cache import OrganizerCachedBundle
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import OrganizerSource
from pastport.domain.organizer_inputs import NativeInputRequest, UploadedProductionStart
from pastport.domain.organizer_review import (
    ObjectReviewHistory, OrganizerReviewBinding, OrganizerReviewObject, OrganizerReviewView,
    ReviewChange, ReviewImage, ReviewEnvironmentResource,
)
from pastport.domain.story_inputs import EnvironmentSnapshot, SpatialPoint

class _Native(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

class _IDMLReviewRow(_Native):
    number: int
    name: str
    historical_name: str | None
    status: Literal["matched", "unmatched", "requires_review"]
    reason: str
    image_role: Literal["object_image", "context_image", "text_evidence"]


class _IDMLReviewGap(_Native):
    object_number: int
    reason: str


class _Object(_Native):
    id: int
    stable_id: str
    name: str
    historical_id: str | None
    rationale: str
    image_review: str
    text_review: str
    version: int

class _Source(_Native):
    id: str
    title_zh: str
    media_path: str
    image_page: int
    exact_text: str | None = None
    text_page: int | None = None
    scope_warning: str

class _Photo(_Native):
    id: int
    filename: str
    media_path: str

class _Observation(_Native):
    id: int
    photo_id: int
    object_id: int

class _History(_Native):
    modern_id: int
    image_verdict: str
    text_verdict: str
    note: str
    reviewer: str
    created_at: str

class _Introduction(_Native):
    object_id: int
    content: str
    version: int

class _Dataset(_Native):
    objects: tuple[_Object, ...] = Field(max_length=1000)
    sources: tuple[_Source, ...] = Field(max_length=1000)
    photos: tuple[_Photo, ...] = Field(max_length=1000)
    observations: tuple[_Observation, ...] = Field(max_length=10000)
    reviews: tuple[_History, ...] = Field(max_length=10000)
    vr_contents: tuple[_Introduction, ...] = Field(max_length=1000)

class _LiveAnchor(_Native):
    id: int
    point_json: str | None
    version: int

class _LiveCandidate(_Native):
    object_id: int
    point_json: str | None

class _LiveAlignment(_Native):
    version: int
    confirmed: bool

class _LiveSpatial(_Native):
    binding: str
    source_scene_id: str
    alignment: _LiveAlignment
    objects: tuple[_LiveAnchor, ...]
    candidates: tuple[_LiveCandidate, ...]

class SDKOrganizerReview:
    def __init__(self, *, include_spatial: bool = True) -> None:
        self.include_spatial = include_spatial

    @staticmethod
    def binding(source: OrganizerSource) -> OrganizerReviewBinding:
        if source.review_binding_file is not None:
            binding = OrganizerReviewBinding.model_validate_json(source.review_binding_file.read_bytes())
        elif source.bundle_file is not None:
            bundle = OrganizerCachedBundle.model_validate_json(source.bundle_file.read_bytes())
            binding = OrganizerReviewBinding(
                root=bundle.native_import.path.parent,
                worlds=tuple(world.attachment.path.parent.parent for world in bundle.worlds),
                import_sha256=bundle.native_import.sha256,
            )
        else:
            raise ServiceError("REVIEW_NOT_PREPARED", "此项目尚未交接原生审核资料，请先准备环境。", 409)
        if binding.root.is_symlink() or BoundedNativeArchive.digest(binding.root / "import-manifest.json") != binding.import_sha256:
            raise ServiceError("REVIEW_SOURCE_CHANGED", "审核来源身份已改变，不能继续。", 409)
        return binding

    def _dataset(self, source: OrganizerSource) -> tuple[OrganizerReviewBinding, _Dataset, str]:
        from pastport_matched_environment.application.shared_content import SharedContentAuthority
        from pastport_matched_environment.application.review_repository import ReviewRepository
        binding = self.binding(source)
        try:
            database = SharedContentAuthority(binding.root).database
            if database.parent.resolve() != binding.root.resolve():
                raise ServiceError("REVIEW_AUTHORITY_SCOPE", "审核库不属于登记的来源。", 403)
            BoundedNativeArchive.database(database)
            raw = ReviewRepository(database).dataset()
            if len(raw.encode()) > 16 * 1024**2:
                raise ServiceError("REVIEW_SIZE_LIMIT", "审核资料超过读取范围。", 413)
            return binding, _Dataset.model_validate_json(raw), hashlib.sha256(raw.encode()).hexdigest()
        except (OSError, ValueError, sqlite3.Error) as error:
            raise ServiceError("REVIEW_UNAVAILABLE", "原生审核资料暂不可用，未改用副本。", 409) from error

    @staticmethod
    def _asset(root: Path, relative: str) -> tuple[str, Path]:
        candidate = root / relative
        path = candidate.resolve()
        if not path.is_relative_to(root.resolve()) or candidate.is_symlink() or not path.is_file():
            raise ServiceError("REVIEW_MEDIA_MISSING", "审核图片缺失或超出登记目录。", 404)
        return "asset-" + hashlib.sha256(str(path).encode()).hexdigest()[:32], path

    def read(self, source: OrganizerSource, request: GameMakingRequest) -> OrganizerReviewView:
        binding, dataset, revision = self._dataset(source)
        snapshot = EnvironmentSnapshot.model_validate_json(request.environment.read_bytes())
        historical = {item.id: item for item in dataset.sources}
        introductions = {item.object_id: item for item in dataset.vr_contents}
        frozen = {item.object_number: item for item in snapshot.objects}
        spatial_revision, current = self._spatial_state(binding, snapshot) if self.include_spatial else ("semantic-fixture", True)
        objects: list[OrganizerReviewObject] = []
        for item in dataset.objects:
            evidence = historical.get(item.historical_id or "")
            introduction = introductions.get(item.id)
            old = frozen.get(item.id)
            if old is not None:
                if old.stable_id != item.stable_id:
                    raise ServiceError("REVIEW_IDENTITY_CHANGED", "物件编号与稳定身份不一致。", 409)
                current = current and old.pairing_version == item.version and old.introduction_version == (introduction.version if introduction else 0)
            photo_ids = {obs.photo_id for obs in dataset.observations if obs.object_id == item.id}
            photos = tuple(ReviewImage(asset_id=self._asset(binding.root, p.media_path)[0], caption=p.filename) for p in dataset.photos if p.id in photo_ids)
            image = ReviewImage(asset_id=self._asset(binding.root, evidence.media_path)[0], caption=(f"IDML原始配图 · {evidence.title_zh}" if snapshot.source_format == "idml" else f"映射来源PDF第{evidence.image_page}页 · {evidence.title_zh}")) if evidence else None
            objects.append(OrganizerReviewObject(
                number=item.id, stable_id=item.stable_id, name=item.name,
                historical_id=item.historical_id, historical_title=evidence.title_zh if evidence else None,
                rationale=item.rationale, image_review=item.image_review, text_review=item.text_review,
                pairing_version=item.version, introduction=introduction.content if introduction else None,
                introduction_version=introduction.version if introduction else None,
                quote=evidence.exact_text if evidence else None, quote_page=evidence.text_page if evidence and snapshot.source_format == "pdf" else None,
                scope_warning=evidence.scope_warning if evidence else "没有配对史料，保留未知。",
                photos=photos, source_image=image,
                history=tuple(ObjectReviewHistory(image=h.image_verdict, text=h.text_verdict, note=h.note, reviewer=h.reviewer, created_at=h.created_at) for h in dataset.reviews if h.modern_id == item.id),
                positions=tuple(position for position in snapshot.positions if position.object_number == item.id),
                locations=tuple(location for world in (snapshot.metric_spatial.worlds if snapshot.metric_spatial else ()) for location in world.objects if location.object_number == item.id),
            ))
        return OrganizerReviewView(source_format=snapshot.source_format, view_count=len(binding.worlds), database_path=(binding.root / "pastport_matching.sqlite3").resolve(), source_id=source.source_id, project_id=source.project_id, title=source.title,
            revision=hashlib.sha256((revision + ":" + spatial_revision + ":" + BoundedNativeArchive.digest(request.environment)).encode()).hexdigest(), snapshot_current=current, objects=tuple(objects))

    def save(self, source: OrganizerSource, request: GameMakingRequest, number: int, change: ReviewChange, actor_id: str) -> None:
        from pastport_matched_environment.application.review_repository import Review, ReviewRepository
        from pastport_matched_environment.application.vr_content import VRContentEdit, VRContentService
        view = self.read(source, request)
        if not any(item.number == number for item in view.objects):
            raise ServiceError("REVIEW_OBJECT_UNKNOWN", "此项目中没有这个物件。", 404)
        database = self.binding(source).root / "pastport_matching.sqlite3"
        try:
            if change.kind == "review":
                saved = ReviewRepository(database).save(Review(number, change.expected_version, change.image, change.text, change.note, actor_id))
            else:
                if not change.content.strip():
                    raise ServiceError("REVIEW_CONTENT_EMPTY", "介绍内容不能为空。", 422)
                saved = VRContentService(database).save(VRContentEdit(number, change.expected_version, change.content, actor_id))
        except sqlite3.Error as error:
            raise ServiceError("REVIEW_SAVE_FAILED", "审核未保存，请稍后再试。", 503) from error
        if not saved:
            raise ServiceError("REVIEW_VERSION_CONFLICT", "资料已被更新，本次没有覆盖；请重新载入后核对。", 409)

    def media(self, source: OrganizerSource, request: GameMakingRequest, asset_id: str) -> Path:
        if asset_id == "original-pdf":
            return request.original_pdf
        binding, dataset, _ = self._dataset(source)
        if asset_id == "mapping-pdf":
            return binding.root / ("source.idml" if request.original_pdf.suffix.lower() == ".idml" else "source.pdf")
        for relative in (*[p.media_path for p in dataset.photos], *[s.media_path for s in dataset.sources]):
            key, path = self._asset(binding.root, relative)
            if key == asset_id:
                return path
        raise ServiceError("REVIEW_ASSET_UNKNOWN", "找不到属于此项目的审核图片。", 404)

    def export(self, source: OrganizerSource, request: GameMakingRequest, actor_id: str, output: Path) -> GameMakingRequest:
        from pastport.adapters.organizer_native import NativeGameInputExporter, NativeWorldSet
        binding = self.binding(source)
        snapshot = EnvironmentSnapshot.model_validate_json(request.environment.read_bytes())
        output.mkdir(parents=True, exist_ok=False)
        # Reuse the registered extraction; applying review never calls PDF/model providers.
        shutil.copyfile(request.source_document, output / "source-document.json")
        native = NativeInputRequest(project_id=source.project_id, owner_id=actor_id, job_id=output.name,
            entry_level="3d", files=(), options=UploadedProductionStart(stop_after="environment"),
            shared_player_assets=request.museum_directory / "assets")
        prepared = NativeGameInputExporter().export(native, NativeWorldSet(binding.root, binding.worlds, snapshot.entry_view_id), request.original_pdf, output, lightweight_review=True)
        (output / "prepared-request.json").write_text(prepared.model_dump_json())
        return prepared


    def _idml_inventory(self, source: OrganizerSource) -> tuple[_IDMLReviewRow, ...]:
        root = self.binding(source).root
        index = root / "idml-review-inventory.json"
        if index.is_file():
            return TypeAdapter(tuple[_IDMLReviewRow, ...]).validate_json(index.read_bytes())
        # Earlier native runs retain the original identity inventory and handoff gaps.
        if root.name != "result" or root.parent.parent.name != "runs" or root.parent.parent.parent.name != "environment-build":
            return ()
        evidence = root.parents[3] / "evidence"
        handoff = evidence / "native-handoff"
        lock = evidence / "idml-input.sha256"
        if not lock.is_file():
            return ()
        digest = lock.read_text().strip()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            return ()
        from pastport_evidence.application.idml_handoff import IDMLEnvironmentHandoff
        from pastport_evidence.domain.idml import IDMLMatchResult
        from pastport_evidence.domain.photos import PhotoInventory

        inventory = PhotoInventory.model_validate_json(
            (evidence / "runs" / digest / "photo-inventory.json").read_bytes()
        )
        matches = IDMLMatchResult.model_validate_json((handoff / "idml-matches.json").read_bytes())
        gaps = TypeAdapter(tuple[_IDMLReviewGap, ...]).validate_json(
            (handoff / "mapping-gaps.json").read_bytes()
        )
        reasons = {gap.object_number: gap.reason for gap in gaps}
        entities = {entity.object_id: entity for entity in inventory.entities}
        conflicts = IDMLEnvironmentHandoff.identity_conflicts(matches, inventory)
        rows = []
        for match in matches.objects:
            entity = entities[match.object_id]
            status = match.status
            if status == "matched" and entity.display_number in reasons:
                status = "requires_review"
            if match.object_id in conflicts:
                status = "requires_review"
                others = ", ".join(map(str, sorted(conflicts[match.object_id])))
                reasons[entity.display_number] = f"现场照片选区与编号 {others} 高度重叠，请复核物件身份。"
            rows.append(_IDMLReviewRow(
                number=entity.display_number, name=entity.label,
                historical_name=match.historical_name, status=status,
                reason=reasons.get(entity.display_number, match.review_reason),
                image_role=match.image_role,
            ))
        return tuple(rows)

    def _idml_inventory_markup(self, source: OrganizerSource) -> str:
        rows = self._idml_inventory(source)
        if not rows:
            return ""
        states = {"matched": "史料候选", "unmatched": "未匹配", "requires_review": "待复核"}
        images = {"object_image": "实物配图候选", "context_image": "背景参考图", "text_evidence": "无已确认实物照"}
        items = []
        for row in sorted(rows, key=lambda item: item.number):
            items.append(
                f"<li><strong>{row.number:02d} · {escape(row.name)}</strong> · {states[row.status]}"
                f"<div>{escape(row.historical_name or '暂无对应历史对象')} · {images[row.image_role]}</div>"
                f"<p>{escape(row.reason)}</p></li>"
            )
        return f"<details><summary>全部识别物件（{len(rows)} 项）</summary><ol>{''.join(items)}</ol></details>"

    def workbench(self, source: OrganizerSource, request: GameMakingRequest, actor_id: str, prefix: str) -> str:
        self.read(source, request)
        # Always render trusted installed UI. Never execute HTML/scripts uploaded with a scene.
        from pastport_matched_environment.application.scene3d_review import shared_review_markup
        template = files("pastport_matched_environment").joinpath("reference_environment/review.html")
        html = shared_review_markup(template.read_text())
        html = html.replace("||1;const $", "||0;const $").replace("))id=1;", "))id=data.objects[0].id;")
        html = html.replace("叙事优先的合成演示：代理可以跨类别，但编号稳定、来源真实。图片关联与文字适用性分别复核。", "当前项目的同源物件审核；图片关联与文字适用性分别复核。保存后请在外层确认本次制作使用的资料版本。")
        snapshot = EnvironmentSnapshot.model_validate_json(request.environment.read_bytes())
        if snapshot.source_format == "idml":
            html = html.replace("PDF 来源对象", "IDML 来源对象")
            html = html.replace("<main>", self._idml_inventory_markup(source) + "<main>", 1)
            html = html.replace("这是原文证据截图，没有已确认的实物照片。", "只有 IDML 原文依据，尚无已确认的实物照片。")
            html = html.replace(
                """${img(s.media_path,s.title_zh)}<p>来源截图：PDF 第 ${s.image_page} 页／印刷页 ${s.image_page+109}；建筑 ${esc(s.building_id)}；父对象 ${esc(s.parent_ref)}</p><a href="media/source-page-${String(s.image_page).padStart(2,'0')}.png" target="_blank">查看完整来源图片页</a>""",
                "${s.image_role==='text_evidence'?'':img(s.media_path,s.title_zh)}",
            )
            html = html.replace("文字：PDF 第 ${s.text_page} 页／印刷页 ${s.text_page+109}。", "IDML原文单元（不是PDF页码）。")
            html = html.replace("原PDF中的对象选区。", "IDML包中的来源图片；语义关联待审核。")
            html = html.replace("英文原文与适用范围", "原文与适用范围")
            html = html.replace("中文译文（人工整理，未独立审校）", "中文介绍（AI草稿，待人工审核）")
            html = html.replace("规范化页面的 Unicode 字符偏移，非 PDF 字节或屏幕坐标。", "IDML原文单元的 Unicode 字符偏移，非排版页码或屏幕坐标。")
            html = html.replace("查看完整来源图片页", "查看来源说明图")
        html = html.replace("${s.image_page+109}", "${s.image_printed_page??'未识别'}").replace("${s.text_page+109}", "${s.text_printed_page??'未识别'}")
        html = html.replace("${esc(last?.reviewer||'')}", escape(actor_id)).replace("${esc(vr.editor==='initial_trial_snapshot'?'':vr.editor)}", escape(actor_id))
        html = html.replace("${esc(vr.editor==='initial_trial_snapshot'?'':vr.editor)}", escape(actor_id))
        html = html.replace("此对象当前没有放置VR热点，因此还没有弹窗内容。05号背包尚未定位；其他未纳入本轮的对象保持原状。", "此对象目前没有可编辑介绍；未确认位置不补造热点。")
        # Drop obsolete demo/export footer; the actual review layout and controls stay intact.
        start = html.find("<section><h3>VR挂载试验</h3>")
        end = html.find("`;", start)
        if start < 0 or end < 0:
            raise ServiceError("REVIEW_TEMPLATE_CHANGED", "原审核界面模板已变化，请维护者核对。", 409)
        html = html[:start] + html[end:]
        html = html.replace('<a href="/vr_trial/index.html" target="_blank">打开VR查看</a>', '<p class="sub">挂载定位保留在环境编辑器中；本页与环境共用介绍和审核数据。</p>')
        html = html.replace("fetch('/api/data')", "fetch('" + prefix + "/data')")
        html = html.replace("fetch('/api/review'", "fetch('" + prefix + "/save-review'")
        html = html.replace("fetch('/api/vr-content'", "fetch('" + prefix + "/save-introduction'")
        html = html.replace("fetch('/api/scene3d/content'", "fetch('" + prefix + "/save-introduction'")
        environment = prefix.rsplit('/workbench', 1)[0] + '/environment/0'
        html = html.replace('href="/scene3d/index.html', 'target="_blank" href="' + environment + '/scene3d/index.html')
        html = html.replace('href="/vr_trial/index.html', 'target="_blank" href="' + environment + '/vr_trial/index.html')
        html = html.replace('src="/scene3d/shared_content.js"', 'src="' + environment + '/shared_content.js"')
        html = html.replace("headers:{'Content-Type':'application/json'}", "headers:{'Content-Type':'application/json','X-PastPort-Edit':'1'}")
        html = html.replace("await load();$('result')", "await load();window.parent.postMessage({type:'pastport-review-saved'},location.origin);$('result')")
        html = html.replace("await load();$('vr-result')", "await load();window.parent.postMessage({type:'pastport-review-saved'},location.origin);$('vr-result')")
        html = html.replace("media/", prefix + "/media/")
        html += "<script>document.addEventListener('input',event=>{if(['vr-content','vr-editor','image','text','reviewer','note'].includes(event.target.id))window.parent.postMessage({type:'pastport-review-dirty'},location.origin);});</script>"
        return html

    def workbench_data(self, source: OrganizerSource) -> str:
        from pastport_matched_environment.application.review_repository import ReviewRepository
        binding, _, _ = self._dataset(source)
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(ReviewRepository(binding.root / "pastport_matching.sqlite3").dataset())
        references = payload.get("references", [])
        if isinstance(references, list):
            for reference in references:
                if isinstance(reference, dict):
                    url = reference.get("url")
                    if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
                        reference["url"] = "#"
        photos = payload.get("photos", [])
        if isinstance(photos, list):
            for photo in photos:
                if isinstance(photo, dict):
                    photo.pop("original_path", None)
        return json.dumps(payload, ensure_ascii=False)

    def workbench_media(self, source: OrganizerSource, relative: str) -> Path:
        binding, dataset, _ = self._dataset(source)
        allowed = {p.media_path.removeprefix("media/") for p in dataset.photos}
        allowed.update(s.media_path.removeprefix("media/") for s in dataset.sources)
        allowed.update(f"observation-{o.id:03}.jpg" for o in dataset.observations)
        allowed.update(f"photo-{p.id:02}.jpg" for p in dataset.photos)
        allowed.update(f"source-page-{s.image_page:02}.png" for s in dataset.sources)
        allowed.update(f"source-page-{s.text_page:02}.png" for s in dataset.sources if s.text_page)
        if relative not in allowed:
            raise ServiceError("REVIEW_ASSET_UNKNOWN", "图片不属于此项目的审核资料。", 404)
        return self._asset(binding.root, "media/" + relative)[1]


    def environment(self, source: OrganizerSource, request: GameMakingRequest, view: int, relative: str, query: str, body: bytes | None, actor_id: str, origin: str) -> ReviewEnvironmentResource:
        from pastport.adapters.organizer_review_environment import SDKReviewEnvironment
        prefix = '/organizer/api/review/' + source.source_id + '/environment'
        try:
            return SDKReviewEnvironment(self.binding(source), prefix, origin).resource(view, relative, query, body, actor_id)
        except (OSError, sqlite3.Error) as error:
            raise ServiceError("REVIEW_ENVIRONMENT_UNAVAILABLE", "环境资料暂不可用；没有保存成功或切换到其它资料。", 503) from error
        except ValueError as error:
            raise ServiceError("REVIEW_ENVIRONMENT_INVALID", "编辑请求与当前场景、位置版本或允许参数不一致。", 422) from error


    @staticmethod
    def _spatial_state(binding: OrganizerReviewBinding, snapshot: EnvironmentSnapshot) -> tuple[str, bool]:
        from pastport_matched_environment.api.scene3d import Scene3DStore
        from pastport_matched_environment.application.scene3d_arrows import Scene3DArrowStore
        from pastport_matched_environment.application.vr_positions import VRPositionService
        digest = hashlib.sha256()
        current = True
        worlds = {world.view_id: world for world in snapshot.metric_spatial.worlds} if snapshot.metric_spatial else {}
        for root in binding.worlds:
            raw = Scene3DStore(root).current()
            payload = _LiveSpatial.model_validate_json(raw)
            digest.update(raw)
            arrows = Scene3DArrowStore(root).current()
            digest.update(arrows.model_dump_json().encode())
            old = worlds.get(payload.source_scene_id)
            if old is None:
                current = False
                continue
            current = current and old.scene_binding == payload.binding and old.calibration.version == payload.alignment.version and old.calibration.confirmed == payload.alignment.confirmed
            anchors = {anchor.id: anchor for anchor in payload.objects}
            candidates = {candidate.object_id: candidate.point_json for candidate in payload.candidates}
            for location in old.objects:
                anchor = anchors.get(location.object_number)
                if anchor is None:
                    current = False
                    continue
                point = anchor.point_json or candidates.get(anchor.id)
                live_point = SpatialPoint.model_validate_json(point) if point else None
                current = current and anchor.version == location.version and live_point == location.point
            old_arrows = {link.hotspot_id: link for link in old.navigation}
            for arrow in arrows.arrows:
                previous = old_arrows.get(arrow.hotspot_id)
                if previous is None or previous.version != arrow.version:
                    current = False
        positions = VRPositionService(binding.root / "pastport_matching.sqlite3", binding.root / "vr_trial/trial_report.json")
        live_positions = positions.current()
        digest.update(positions.encode(live_positions).encode())
        known = {(position.object_number, position.view_id): position for position in snapshot.positions}
        for position in live_positions:
            previous_position = known.get((position.key.object_id, position.key.scene_id))
            if previous_position is not None:
                current = current and previous_position.version == position.version and previous_position.yaw == position.yaw and previous_position.pitch == position.pitch
        return digest.hexdigest(), current
