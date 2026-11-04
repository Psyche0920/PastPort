"""Authenticated resources for the existing SDK VR and 3D editors."""

import hashlib
import json
import re
from collections.abc import Callable
from html import escape
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from pydantic import JsonValue, TypeAdapter

from pastport.application.models import ServiceError
from pastport.domain.organizer_review import OrganizerReviewBinding, ReviewEnvironmentResource
from pastport.ports.organizer import MountedEnvironmentPreviews

_JSON = TypeAdapter(dict[str, JsonValue])


class SDKReviewEnvironment:
    def __init__(self, binding: OrganizerReviewBinding, prefix: str, origin: str) -> None:
        self.binding, self.prefix, self.origin = binding, prefix, origin.rstrip("/")

    @staticmethod
    def _json(value: object, status: int = 200) -> ReviewEnvironmentResource:
        return ReviewEnvironmentResource(
            body=json.dumps(value, ensure_ascii=False).encode(),
            media_type="application/json",
            status=status,
        )

    def _script(self, text: str, base: str, review: str) -> str:
        text = (
            text.replace("'/api/", "'" + base + "/api/")
            .replace('"/api/', '"' + base + "/api/")
            .replace("`/api/", "`" + base + "/api/")
        )
        text = text.replace(
            "'Content-Type':'application/json'",
            "'Content-Type':'application/json','X-PastPort-Edit':'1'",
        )
        text = text.replace(
            "'Content-Type': 'application/json'",
            "'Content-Type': 'application/json', 'X-PastPort-Edit':'1'",
        )
        text = text.replace("`/?object_id=${o.id}`", "`" + review + "?object_id=${o.id}`")
        return text

    def resource(
        self, view: int, relative: str, query: str, body: bytes | None, actor_id: str
    ) -> ReviewEnvironmentResource:
        from pastport_matched_environment.application.shared_content import SharedContentAuthority

        if view not in range(len(self.binding.worlds)) or ".." in Path(relative).parts:
            raise ServiceError("REVIEW_VIEW_UNKNOWN", "此视点不属于当前环境。", 404)
        root = self.binding.worlds[view]
        if (
            SharedContentAuthority(root).database.resolve()
            != (self.binding.root / "pastport_matching.sqlite3").resolve()
        ):
            raise ServiceError("REVIEW_AUTHORITY_SCOPE", "视点未绑定当前审核来源。", 403)
        base = self.prefix + "/" + str(view)
        review = self.prefix.rsplit("/environment", 1)[0] + "/workbench/"
        if relative.startswith("api/"):
            return self._api(root, relative[4:], query, body, actor_id)
        if body is not None:
            raise ServiceError("REVIEW_METHOD_INVALID", "此资源不接受修改。", 405)
        assets = files("pastport_matched_environment").joinpath("scene3d_assets")
        if relative == "scene3d/portal-navigation.json":
            return self._json({"endpoint": self.origin + base + "/api/navigation"})
        if relative in ("navigation_boundary.js", "shared_content.js"):
            return ReviewEnvironmentResource(
                body=self._script(assets.joinpath(relative).read_text(), base, review).encode(),
                media_type="text/javascript",
            )
        if relative.startswith("scene3d/"):
            name = relative.removeprefix("scene3d/")
            trusted = {
                "index.html",
                "viewer.js",
                "transitions.js",
                "shared_content.js",
                "navigation_boundary.js",
                "spark.module.js",
                "three.module.js",
                "three.core.js",
                "GLTFLoader.js",
                "Pass.js",
                "BufferGeometryUtils.js",
            }
            if name in trusted:
                text = assets.joinpath(name).read_text()
                if name == "index.html":
                    text = (
                        text.replace('href="/"', 'href="' + review + '"')
                        .replace('href="/vr_trial/', 'href="' + base + "/vr_trial/")
                        .replace('src="/shared_content.js"', 'src="' + base + '/shared_content.js"')
                    )
                    text = text.replace(
                        '<a href="/api/scene3d-export">下载成品</a>',
                        "<span>成品由制作流程统一组包</span>",
                    )
                if name == "transitions.js":
                    text = text.replace(
                        "!/^\\/api\\/scene3d-navigation\\/[a-f0-9]{32}$/.test(endpoint.pathname)",
                        "endpoint.pathname!==" + json.dumps(base + "/api/navigation"),
                    )
                    # Destination checks remain source-scoped after relocating the SDK viewer.
                    pattern = "^" + re.escape(self.prefix) + r"/[01]/scene3d/index\.html$"
                    text = text.replace(
                        "!/^\\/scene3d-results\\/[a-f0-9]{32}\\/$/.test(url.pathname)",
                        "!new RegExp(" + json.dumps(pattern) + ").test(url.pathname)",
                    )
                text = self._script(text, base, review)
                return ReviewEnvironmentResource(
                    body=text.encode(),
                    media_type="text/html" if name.endswith(".html") else "text/javascript",
                )
            binaries = {
                "scene.json",
                "attachment.json",
                "scene.spz",
                "scene-full.spz",
                "scene-styled.spz",
                "style-variant.json",
                "style-panorama.png",
                "collider.glb",
                "panorama.jpg",
                "source-panorama.jpg",
                "source-panorama.png",
            }
            if name in binaries:
                path = root / "scene3d" / name
                if path.is_symlink() or not path.is_file():
                    raise ServiceError("REVIEW_ASSET_MISSING", "视点资源缺失。", 404)
                return ReviewEnvironmentResource(path=path)
        if relative == "vr_trial/vr_position_editor.js":
            text = (
                files("pastport_matched_environment")
                .joinpath("reference_environment/vr_position_editor.js")
                .read_text()
            )
            return ReviewEnvironmentResource(
                body=self._script(text, base, review).encode(), media_type="text/javascript"
            )
        if relative == "vr_trial/index.html":
            source = self.binding.root / "vr_trial/index.html"
            if source.stat().st_size > 64 * 1024**2:
                raise ServiceError("REVIEW_TOUR_TOO_LARGE", "全景数据超过读取范围。", 413)
            match = re.search(
                r'<script id="tour-data" type="application/json">(.*?)</script>',
                source.read_text(),
                re.S,
            )
            if match is None:
                raise ServiceError("REVIEW_TOUR_MISSING", "没有可复用的全景数据。", 409)
            data = _JSON.validate_json(match[1])
            scenes = data.get("scenes")
            if not isinstance(scenes, list):
                raise ServiceError("REVIEW_TOUR_INVALID", "全景场景数据格式不正确。", 422)
            for scene in scenes:
                if not isinstance(scene, dict):
                    raise ServiceError("REVIEW_TOUR_INVALID", "全景场景数据格式不正确。", 422)
                panorama = scene.get("panorama")
                encoded_image = panorama.get("data") if isinstance(panorama, dict) else None
                if not isinstance(encoded_image, str) or not encoded_image.startswith(
                    ("data:image/jpeg;base64,", "data:image/png;base64,")
                ):
                    raise ServiceError(
                        "REVIEW_TOUR_INVALID", "全景只能使用项目内已登记的JPEG/PNG图像。", 422
                    )
                for key in ("name", "description"):
                    if isinstance(scene.get(key), str):
                        scene[key] = escape(str(scene[key]))
                hotspots = scene.get("hotspots", [])
                if isinstance(hotspots, list):
                    for hotspot in hotspots:
                        if isinstance(hotspot, dict):
                            for key in ("label", "text"):
                                if isinstance(hotspot.get(key), str):
                                    hotspot[key] = escape(str(hotspot[key]))
                            for key in ("url", "href", "clickHandlerFunc", "createTooltipFunc"):
                                hotspot.pop(key, None)
            encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
            text = (
                files("pastport_matched_environment")
                .joinpath("reference_environment/viewer.html")
                .read_text()
            )
            text = text.replace(
                '<script id="tour-data" type="application/json">{}</script>',
                '<script id="tour-data" type="application/json">' + encoded + "</script>",
            )
            text = self._script(text, base, review)
            text = text.replace(
                "new window.PastPortPositionEditor(r).initialize();",
                (
                    "new window.PastPortPositionEditor(r).initialize();window.Pas"
                    'tPortSourceHost=r;window.dispatchEvent(new Event("pastport-s'
                    'ource-ready"));'
                ),
            )
            text += '\n<script src="' + base + '/shared_content.js"></script>'
            return ReviewEnvironmentResource(body=text.encode(), media_type="text/html")
        raise ServiceError("REVIEW_ASSET_UNKNOWN", "此资源不属于当前环境编辑器。", 404)

    def _api(
        self, root: Path, route: str, query: str, body: bytes | None, actor_id: str
    ) -> ReviewEnvironmentResource:
        from pastport_matched_environment.api.scene3d import Scene3DStore
        from pastport_matched_environment.application.navigation import (
            NavigationEdit,
            NavigationStore,
        )
        from pastport_matched_environment.application.review_repository import ReviewRepository
        from pastport_matched_environment.application.scene3d_arrows import Scene3DArrowStore
        from pastport_matched_environment.application.vr_content import VRContentService
        from pastport_matched_environment.application.vr_positions import (
            PositionEdit,
            VRPositionService,
        )
        from pastport_matched_environment.domain.scene3d import (
            AlignmentEdit,
            AnchorEdit,
            Scene3DArrowEdit,
            SceneCandidateBatch,
        )

        database = self.binding.root / "pastport_matching.sqlite3"
        positions = VRPositionService(database, self.binding.root / "vr_trial/trial_report.json")
        if body is None:
            if route == "scene3d":
                return ReviewEnvironmentResource(
                    body=Scene3DStore(root).current(), media_type="application/json"
                )
            if route == "scene3d/arrows":
                value = _JSON.validate_json(Scene3DArrowStore(root).current().model_dump_json())
                arrows = value.get("arrows", [])
                if isinstance(arrows, list):
                    for arrow in arrows:
                        if not isinstance(arrow, dict):
                            continue
                        for index, world in enumerate(self.binding.worlds):
                            attachment = _JSON.validate_json(
                                (world / "scene3d/attachment.json").read_bytes()
                            )
                            if attachment.get("source_scene_id") == arrow.get("target_scene_id"):
                                arrival = parse_qs(urlsplit(str(arrow.get("target_url", ""))).query)
                                query_string = urlencode(
                                    {
                                        key: arrival[key][0]
                                        for key in ("arrival_yaw", "arrival_pitch")
                                        if key in arrival
                                    }
                                )
                                arrow["target_url"] = (
                                    self.origin
                                    + self.prefix
                                    + "/"
                                    + str(index)
                                    + "/scene3d/index.html"
                                    + ("?" + query_string if query_string else "")
                                )
                return self._json(value)
            if route == "vr-positions":
                return ReviewEnvironmentResource(
                    body=positions.encode(positions.current()).encode(),
                    media_type="application/json",
                )
            if route == "vr-navigation":
                return self._json(
                    [item.model_dump() for item in NavigationStore(self.binding.root).current()]
                )
            if route in ("scene3d/content", "vr-content"):
                try:
                    number = int(parse_qs(query).get("object_id", [""])[0])
                except ValueError as error:
                    raise ServiceError("REVIEW_OBJECT_UNKNOWN", "物件编号无效。", 422) from error
                content = VRContentService(database).read(number)
                if content is None:
                    raise ServiceError("REVIEW_CONTENT_MISSING", "此编号没有当前有效介绍。", 404)
                return ReviewEnvironmentResource(
                    body=content.json().encode(), media_type="application/json"
                )
            if route == "shared-content-revision":
                dataset_json = ReviewRepository(database).dataset()
                payload = _JSON.validate_json(dataset_json)
                objects = payload.get("objects", [])
                eligible = (
                    [
                        item["id"]
                        for item in objects
                        if isinstance(item, dict)
                        and item.get("historical_id")
                        and item.get("image_review") != "unsuitable"
                        and item.get("text_review") != "unsuitable"
                        and item.get("proposal_state") != "invalid_structural_relation"
                    ]
                    if isinstance(objects, list)
                    else []
                )
                return self._json(
                    {
                        "revision": hashlib.sha256(dataset_json.encode()).hexdigest(),
                        "eligible": eligible,
                    }
                )
            if route == "navigation":
                return self._json({})
            raise ServiceError("REVIEW_ROUTE_UNKNOWN", "此编辑接口不可用。", 404)
        payload = _JSON.validate_json(body)
        if "editor" in payload:
            payload["editor"] = actor_id
        raw = json.dumps(payload).encode()
        if route == "scene3d/anchor":
            saved = Scene3DStore(root).save_anchor(AnchorEdit.model_validate_json(raw))
        elif route == "scene3d/alignment":
            saved = Scene3DStore(root).save_alignment(AlignmentEdit.model_validate_json(raw))
        elif route == "scene3d/candidates":
            saved = Scene3DStore(root).save_candidates(SceneCandidateBatch.model_validate_json(raw))
        elif route == "scene3d/arrows/position":
            saved_arrow = Scene3DArrowStore(root).save(Scene3DArrowEdit.model_validate_json(raw))
            return self._json(
                self._arrow_url(_JSON.validate_json(saved_arrow.model_dump_json()))
                if saved_arrow
                else {"saved": False},
                200 if saved_arrow else 409,
            )
        elif route == "vr-positions":
            position = positions.save(PositionEdit.parse(payload))
            return ReviewEnvironmentResource(
                body=positions.encode((position,) if position else ()).encode(),
                media_type="application/json",
                status=200 if position else 409,
            )
        elif route == "vr-navigation":
            navigation = NavigationStore(self.binding.root).save(
                NavigationEdit.model_validate_json(raw)
            )
            return self._json(
                navigation.model_dump() if navigation else {"saved": False},
                200 if navigation else 409,
            )
        else:
            raise ServiceError("REVIEW_ROUTE_UNKNOWN", "此修改接口不可用。", 404)
        return self._json({"saved": saved}, 200 if saved else 409)

    def _arrow_url(self, arrow: dict[str, JsonValue]) -> dict[str, JsonValue]:
        for index, world in enumerate(self.binding.worlds):
            attachment = _JSON.validate_json((world / "scene3d/attachment.json").read_bytes())
            if attachment.get("source_scene_id") == arrow.get("target_scene_id"):
                arrival = parse_qs(urlsplit(str(arrow.get("target_url", ""))).query)
                query = urlencode(
                    {
                        key: arrival[key][0]
                        for key in ("arrival_yaw", "arrival_pitch")
                        if key in arrival
                    }
                )
                arrow["target_url"] = (
                    self.origin
                    + self.prefix
                    + "/"
                    + str(index)
                    + "/scene3d/index.html"
                    + ("?" + query if query else "")
                )
        return arrow


class SDKMountedPreviewPool:
    """Lazily compose the SDK pool and preserve its owned-process lifecycle."""

    def __init__(self, factory: Callable[[], MountedEnvironmentPreviews] | None = None) -> None:
        self._factory = factory or self._create
        self._pool: MountedEnvironmentPreviews | None = None

    @staticmethod
    def _create() -> MountedEnvironmentPreviews:
        from pastport_matched_environment.application.reference_preview import ReferencePreviewPool

        return ReferencePreviewPool()

    async def ensure(self, root: Path) -> int:
        if self._pool is None:
            self._pool = self._factory()
        return await self._pool.ensure(root)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
