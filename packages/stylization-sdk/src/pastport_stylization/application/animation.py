"""Complete-sphere animation of a labelled reference museum, without source writes."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import json
import math
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from pastport_matched_environment.adapters.execution import SubscriptionExecutor
from pastport_matched_environment.application.reference_environment import (
    Json,
    Record,
    integer,
    read_json,
    record,
    reference_assets,
    sequence,
    string,
    write_json,
)
from pastport_matched_environment.domain.animation import (
    AnimationImageCommand,
    AnimationImageResult,
    ExistingPanorama,
)
from pastport_matched_environment.domain.execution import ExecutionDenied, ExecutionInput, SubscriptionGrant
from pastport_matched_environment.domain.models import DomainModel
from pastport_matched_environment.ports.execution import ImageTransport
from PIL import Image

FACE_ORDER = ("right", "left", "up", "down", "front", "back")
RENDER_ORDER = ("front", "right", "back", "left", "up", "down")
SLOT = r'(<script id="tour-data" type="application/json">)(.*?)(</script>)'


class AnimationRun(DomainModel):
    source_directory: str
    workspace: str
    grant: SubscriptionGrant | None = None
    existing_panoramas: tuple[ExistingPanorama, ...] = ()
    resume: bool = False


class AnimationDelivery(DomainModel):
    environment: str
    archive: str
    manifest: str
    viewpoint_count: int
    acceptance: str = "candidate_pending_seam_identity_hotspot_and_device_review"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256")
    return checksum.hexdigest()


class AnimationWorkflow:
    """Bound all model turns before work; keep source data and interaction bindings intact."""

    def __init__(
        self,
        ffmpeg: Path | None,
        style: Path,
        prompt: Path,
        transport: ImageTransport | None,
        *,
        ledger_path: Path | None = None,
        repair_references: Mapping[str, Path] | None = None,
    ) -> None:
        self._ffmpeg, self._style, self._prompt, self._transport = ffmpeg, style, prompt, transport
        self._ledger_path = ledger_path
        self._repair_references = dict(repair_references or {})

    def run(self, command: AnimationRun) -> AnimationDelivery:
        source = Path(command.source_directory).resolve(strict=True)
        workspace = Path(command.workspace).resolve()
        if workspace == source or workspace.is_relative_to(source):
            raise ExecutionDenied("Animation workspace must be outside the source museum")
        workspace.parent.mkdir(parents=True, exist_ok=True)
        lock_path = workspace.parent / f".{workspace.name}.animation.lock"
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ExecutionDenied("Another animation run owns this workspace") from error
            try:
                return self._run(command)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _run(self, command: AnimationRun) -> AnimationDelivery:
        source = Path(command.source_directory).resolve(strict=True)
        workspace = Path(command.workspace).resolve()
        if workspace == source or workspace.is_relative_to(source):
            raise ExecutionDenied("Animation workspace must be outside the source museum")
        source_html = source / "vr_trial/index.html"
        if source_html.stat().st_size > 200 * 1024 * 1024:
            raise ExecutionDenied("Tour HTML exceeds the supported 200 MiB bound")
        matches = list(re.finditer(SLOT, source_html.read_text(), re.S))
        if len(matches) != 1:
            raise ExecutionDenied("Expected one data-only tour payload")
        tour = record(json.loads(matches[0][2]))
        if tour.get("schemaVersion") != 4:
            raise ExecutionDenied("Animation currently accepts labelled schema-4 reference museums")
        scenes = [record(item) for item in sequence(tour["scenes"])]
        if not 1 <= len(scenes) <= 100:
            raise ExecutionDenied("A museum must have between 1 and 100 viewpoints")
        ids = [string(scene["id"]) for scene in scenes]
        if len(set(ids)) != len(ids) or tour.get("firstSceneId") not in ids:
            raise ExecutionDenied("Invalid scene identities or first-scene binding")
        for scene in scenes:
            for hotspot in sequence(scene["hotspots"]):
                item = record(hotspot)
                if item.get("type") == "scene" and item.get("targetId") not in ids:
                    raise ExecutionDenied("Navigation target is outside the input museum")
        if not any(
            record(h).get("type") == "info" for s in scenes for h in sequence(s["hotspots"])
        ):
            raise ExecutionDenied("Input must already contain object labels and introductions")
        if workspace.exists() and not command.resume:
            raise ExecutionDenied("Workspace already exists; use explicit resume for the same run")
        workspace.mkdir(parents=True, exist_ok=command.resume)
        executor: SubscriptionExecutor | None = None
        reuse = {image.scene_id: image for image in command.existing_panoramas}
        if command.existing_panoramas:
            if len(reuse) != len(command.existing_panoramas) or set(reuse) != set(ids):
                raise ExecutionDenied("Existing images must bind every viewpoint exactly once")
            for scene in scenes:
                self._check_existing(scene, reuse[string(scene["id"])])
        else:
            if command.grant is None or self._transport is None:
                raise ExecutionDenied(
                    "Generation requires an explicit subscription grant/transport"
                )
            executor = SubscriptionExecutor(
                self._ledger_path or workspace / "usage.sqlite3", command.grant, self._transport
            )
            remaining = executor.remaining_calls()
            if not command.resume and remaining < len(scenes) * 6:
                raise ExecutionDenied("Grant must cover six directional turns per viewpoint")
        output = workspace / "environment"
        frozen_style = workspace / "style.png"
        frozen_prompt = workspace / "prompt.txt"
        binding_path = workspace / "run-binding.json"
        source_hash = digest(source_html)
        expected: Record = {
            "source_directory": str(source),
            "source_html_sha256": source_hash,
            "style_sha256": digest(self._style),
            "prompt_sha256": digest(self._prompt),
            "existing_panoramas": [
                json.loads(image.model_dump_json()) for image in command.existing_panoramas
            ],
        }
        if command.resume:
            if record(read_json(binding_path)) != expected:
                raise ExecutionDenied("Resume input/style/prompt binding changed")
            if digest(frozen_style) != expected["style_sha256"]:
                raise ExecutionDenied("Frozen style changed")
            if digest(frozen_prompt) != expected["prompt_sha256"]:
                raise ExecutionDenied("Frozen prompt changed")
            tour = record(read_json(workspace / "input-tour.json"))
            scenes = [record(item) for item in sequence(tour["scenes"])]
            original = json.dumps(tour, ensure_ascii=False, sort_keys=True)
        else:
            # Validate every sphere before the first model dispatch.
            for scene in scenes:
                raw = self._image_bytes(string(record(scene["panorama"])["data"]))
                with Image.open(io.BytesIO(raw)) as image:
                    width, height = image.size
                    image.verify()
                if width != height * 2 or width * height > 64_000_000:
                    raise ExecutionDenied("Expected bounded full 2:1 spheres")
            if not reuse:
                if command.grant is None or self._transport is None:
                    raise ExecutionDenied("Missing subscription generation authorization")
                capabilities = self._transport.capabilities(command.grant.model_id, workspace)
                if not (
                    capabilities.authenticated
                    and capabilities.image_generation
                    and capabilities.requested_model_available
                ):
                    raise ExecutionDenied("Subscription model or image generation unavailable")
            self._snapshot(source, output)
            self._apply_current_edits(output, scenes)
            original = json.dumps(tour, ensure_ascii=False, sort_keys=True)
            (workspace / "input-tour.json").write_text(original)
            shutil.copyfile(self._style, frozen_style)
            shutil.copyfile(self._prompt, frozen_prompt)
            write_json(binding_path, expected)
        calls_before = executor.reserved_calls() if executor else 0
        rows: list[Json] = []
        first_faces: dict[str, Path] = {}
        for index, scene in enumerate(scenes):
            if reuse:
                row = self._reuse(index, scene, workspace, reuse[string(scene["id"])])
            else:
                if executor is None:
                    raise ExecutionDenied("Generation executor is missing")
                row = self._scene(
                    index, scene, workspace, frozen_style, frozen_prompt, first_faces, executor
                )
            rows.append(row)
        # No model is allowed to author tour JSON; only panorama bytes and revision change.
        self._verify_semantics(original, tour)
        self._render(output, tour)
        self._render_review(source, output, tour)
        self._update_report(output, scenes, original)
        manifest: Record = {
            "workflow": "animated-museum-v1",
            "execution_mode": "reuse_existing_images" if reuse else "subscription_generation",
            "new_model_calls": executor.reserved_calls() - calls_before if executor else 0,
            "source_html_sha256": source_hash,
            "style_sha256": digest(frozen_style),
            "prompt_sha256": digest(frozen_prompt),
            "face_order": list(FACE_ORDER),
            "padding": 0.05,
            "views": rows,
            "source_database_sha256": digest(output / "pastport_matching.sqlite3"),
            "acceptance": "candidate_pending_seam_identity_hotspot_and_device_review",
            "pixel_reproducibility": "not_guaranteed_by_stochastic_image_generation",
        }
        write_json(output / "animation-manifest.json", manifest)
        (output / "STORY_AGENT_HANDOFF.md").write_text(
            "# Animated museum\n\nOpen vr_trial/index.html. The original identities, evidence, "
            "introductions, navigation and human edits are retained. Generated visual details "
            "are illustrative, never historical evidence. Read animation-manifest.json for "
            "source hashes, native face dimensions and pending checks. Original hotspot angles "
            "are proposals on new textures; check them visually. No formal seam, device or "
            "object-position acceptance is implied. The source museum was not overwritten.\n"
        )
        archive = shutil.make_archive(
            str(workspace / "animated-museum"), "zip", workspace, output.name
        )
        return AnimationDelivery(
            environment=str(output),
            archive=archive,
            manifest=str(output / "animation-manifest.json"),
            viewpoint_count=len(scenes),
        )

    @staticmethod
    def _snapshot(source: Path, output: Path) -> None:
        output.mkdir()
        allowed = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".json", ".csv"}
        total = 0
        count = 0
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ExecutionDenied("Museum input cannot contain symlinks")
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            if any(part.startswith(".") for part in path.relative_to(source).parts):
                continue
            total += path.stat().st_size
            count += 1
            if total > 1024 * 1024 * 1024 or count > 10000:
                raise ExecutionDenied("Museum source bundle exceeds bounded copy limits")
            target = output / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        database = source / "pastport_matching.sqlite3"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(output / database.name)) as dst:
                src.backup(dst)
        reference = reference_assets()
        (output / "vr_trial").mkdir(exist_ok=True)
        for name in ("review_server", "vr_content", "vr_positions", "start_demo"):
            shutil.copyfile(reference / f"{name}.py.template", output / f"{name}.py")
        shutil.copyfile(
            reference / "vr_position_editor.js", output / "vr_trial/vr_position_editor.js"
        )
        shutil.copyfile(reference / "review.html", output / "index.html")

    @staticmethod
    def _apply_current_edits(output: Path, scenes: list[Record]) -> None:
        with closing(sqlite3.connect(output / "pastport_matching.sqlite3")) as db:
            for scene in scenes:
                for value in sequence(scene["hotspots"]):
                    hotspot = record(value)
                    identifier = str(hotspot.get("id", ""))
                    if not identifier.startswith("trial-object-"):
                        continue
                    number = int(identifier.removeprefix("trial-object-"))
                    row = db.execute(
                        "SELECT COALESCE(human_override,ai_draft) FROM vr_display_contents "
                        "WHERE object_id=?",
                        (number,),
                    ).fetchone()
                    if row and row[0] is not None:
                        hotspot["text"] = str(row[0])
                    # Respect current human coordinates without carrying approval to new media.
                    panorama = record(scene["panorama"])
                    raw = AnimationWorkflow._image_bytes(string(panorama["data"]))
                    position = db.execute(
                        "SELECT COALESCE(human_yaw,model_yaw),COALESCE(human_pitch,model_pitch) "
                        "FROM vr_positions WHERE object_id=? AND scene_id=? "
                        "AND panorama_revision=? AND panorama_sha256=?",
                        (
                            number,
                            string(scene["id"]),
                            integer(scene["panoramaRevision"]),
                            hashlib.sha256(raw).hexdigest(),
                        ),
                    ).fetchone()
                    if position:
                        hotspot["yaw"], hotspot["pitch"] = float(position[0]), float(position[1])

    @staticmethod
    def _image_bytes(data: str) -> bytes:
        if not data.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
            raise ExecutionDenied("Reference museum panorama must be embedded JPEG or PNG")
        if len(data) > 64 * 1024 * 1024:
            raise ExecutionDenied("Panorama encoded data exceeds the bound")
        return base64.b64decode(data.split(",", 1)[1], validate=True)

    @staticmethod
    def _check_existing(scene: Record, image: ExistingPanorama) -> tuple[int, int, str]:
        raw = AnimationWorkflow._image_bytes(string(record(scene["panorama"])["data"]))
        if hashlib.sha256(raw).hexdigest() != image.source_panorama_sha256:
            raise ExecutionDenied("Existing image belongs to a different source panorama")
        path = Path(image.image_path).resolve(strict=True)
        if path.stat().st_size > 48 * 1024 * 1024 or digest(path) != image.image_sha256:
            raise ExecutionDenied("Existing panorama hash/size binding failed")
        with Image.open(io.BytesIO(raw)) as original:
            expected_size = original.size
        with Image.open(path) as prepared:
            width, height = prepared.size
            media_type = Image.MIME.get(prepared.format or "", "")
            if prepared.format not in ("JPEG", "PNG"):
                raise ExecutionDenied("Existing panorama must be JPEG or PNG")
            prepared.verify()
        if (width, height) != expected_size or width != height * 2:
            raise ExecutionDenied("Existing panorama must retain the source sphere dimensions")
        return width, height, media_type

    @staticmethod
    def _reuse(index: int, scene: Record, workspace: Path, image: ExistingPanorama) -> Record:
        width, height, media_type = AnimationWorkflow._check_existing(scene, image)
        directory = workspace / f"view-{index:03d}"
        directory.mkdir(exist_ok=True)
        target = directory / (
            "animated-panorama.jpg" if media_type == "image/jpeg" else "animated-panorama.png"
        )
        shutil.copyfile(image.image_path, target)
        if digest(target) != image.image_sha256:
            raise ExecutionDenied("Existing image changed during copy")
        panorama = record(scene["panorama"])
        panorama["data"] = (
            f"data:{media_type};base64," + base64.b64encode(target.read_bytes()).decode()
        )
        panorama["width"], panorama["height"] = width, height
        scene["panoramaRevision"] = integer(scene["panoramaRevision"]) + 1
        return {
            "scene_id": scene["id"],
            "source_sha256": image.source_panorama_sha256,
            "output_sha256": image.image_sha256,
            "width": width,
            "height": height,
            "panorama_revision": scene["panoramaRevision"],
            "method": "existing_generated_panorama_reused_without_new_inference",
            "provenance_ref": image.provenance_ref,
        }

    def _project(self, source: Path, target: Path, conversion: str) -> None:
        if self._ffmpeg is None:
            raise ExecutionDenied("New image generation requires FFmpeg with v360")
        subprocess.run(
            [
                str(self._ffmpeg),
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vf",
                conversion,
                "-frames:v",
                "1",
                str(target),
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )

    def _scene(
        self,
        index: int,
        scene: Record,
        workspace: Path,
        style: Path,
        prompt: Path,
        first_faces: dict[str, Path],
        executor: SubscriptionExecutor,
    ) -> Record:
        directory = workspace / f"view-{index:03d}"
        directory.mkdir(exist_ok=True)
        raw = self._image_bytes(string(record(scene["panorama"])["data"]))
        source = directory / "source-image"
        source.write_bytes(raw)
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            image.verify()
        if width != height * 2 or width * height > 64_000_000:
            raise ExecutionDenied("Expected bounded full 2:1 sphere")
        size = math.ceil(width / 3.2)
        cube = directory / "source-cube.png"
        self._project(
            source, cube, f"v360=input=equirect:output=c6x1:out_pad=0.05:w={6 * size}:h={size}"
        )
        with Image.open(cube) as image:
            for offset, name in enumerate(FACE_ORDER):
                image.crop((offset * size, 0, (offset + 1) * size, size)).save(
                    directory / f"{name}.png"
                )
        images: dict[str, Path] = {}
        receipts: list[Json] = []
        native_size: int | None = None
        for face in RENDER_ORDER:
            references = [directory / f"{face}.png", style]
            if face in first_faces:
                references.append(first_faces[face])
            elif "front" in images:
                references.append(images["front"])
            previous = self._repair_references.get(string(scene["id"]))
            if previous is not None:
                references.append(previous)
            text = prompt.read_text().replace("{direction}", face)
            text += (
                f"\nAuthorized run budget: at most {executor.grant.max_calls} image turns; "
                f"{executor.remaining_calls()} remaining before this turn. "
                f"Recorded-token threshold {executor.grant.max_recorded_tokens}; "
                f"remaining recorded-token admission {executor.remaining_recorded_tokens()}. "
                "Produce exactly one image for this direction. Do not add variants, "
                "follow-up image generations, provider changes or extra repair runs."
            )
            minimum = math.ceil(width / (4 * 0.9))
            config = AnimationImageCommand(
                output_directory=str(directory / f"generated-{face}"),
                minimum_width=minimum,
                minimum_height=minimum,
            )
            pending_request = ExecutionInput(
                project_id=executor.grant.project_id,
                grant_ref=executor.grant.grant_ref,
                model_id=executor.grant.model_id,
                kind="animation_generation",
                prompt_version="animated-museum-v1",
                policy_version="identity-preserving-v1",
                instructions=text,
                payload_json=config.model_dump_json(),
                output_schema_json=json.dumps(AnimationImageResult.model_json_schema()),
                image_paths=tuple(str(p) for p in references),
                image_hashes=tuple(digest(p) for p in references),
            )
            frozen_request = directory / f"{face}-execution.json"
            if frozen_request.is_file():
                cached_request = ExecutionInput.model_validate_json(frozen_request.read_bytes())
                if (
                    cached_request.image_paths != pending_request.image_paths
                    or cached_request.image_hashes != pending_request.image_hashes
                    or cached_request.payload_json != pending_request.payload_json
                ):
                    raise ExecutionDenied("Frozen directional request binding changed")
                pending_request = cached_request
            else:
                frozen_request.write_text(pending_request.model_dump_json())
            response = executor.execute(pending_request)
            result = AnimationImageResult.model_validate_json(response.payload_json)
            if result.status != "generated" or result.image_path is None:
                raise ExecutionDenied(result.reason or "Native image generation was rejected")
            if native_size is not None and native_size != result.width:
                raise ExecutionDenied("Directional textures have inconsistent native dimensions")
            native_size = result.width
            image_path = Path(result.image_path)
            if not image_path.is_file() or digest(image_path) != result.sha256:
                raise ExecutionDenied("Cached generated image is missing or changed; no redispatch")
            images[face] = image_path
            if index == 0:
                first_faces[face] = images[face]
            receipts.append(
                {
                    "direction": face,
                    "receipt_ref": response.receipt_ref,
                    "sha256": result.sha256,
                    "width": result.width,
                    "height": result.height,
                }
            )
        assert native_size is not None
        with Image.new("RGB", (native_size * 6, native_size)) as strip:
            for offset, face in enumerate(FACE_ORDER):
                with Image.open(images[face]) as image:
                    strip.paste(image.convert("RGB"), (offset * native_size, 0))
            strip.save(directory / "generated-cube.png")
        panorama = directory / "animated-panorama.png"
        self._project(
            directory / "generated-cube.png",
            panorama,
            f"v360=input=c6x1:output=equirect:in_pad=0.05:w={width}:h={height}",
        )
        jpeg = directory / "animated-panorama.jpg"
        with Image.open(panorama) as image:
            image.convert("RGB").save(jpeg, quality=94)
        revised = record(scene["panorama"])
        revised["data"] = "data:image/jpeg;base64," + base64.b64encode(jpeg.read_bytes()).decode()
        revised["width"], revised["height"] = width, height
        scene["panoramaRevision"] = integer(scene["panoramaRevision"]) + 1
        return {
            "scene_id": scene["id"],
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "output_sha256": digest(jpeg),
            "width": width,
            "height": height,
            "panorama_revision": scene["panoramaRevision"],
            "native_faces": receipts,
        }

    @staticmethod
    def _verify_semantics(original: str, tour: Record) -> None:
        previous = record(json.loads(original))
        current = record(json.loads(json.dumps(tour)))
        for data in (previous, current):
            for value in sequence(data["scenes"]):
                scene = record(value)
                scene.pop("panoramaRevision", None)
                panorama = record(scene["panorama"])
                for key in ("data", "width", "height"):
                    panorama.pop(key, None)
        if previous != current:
            raise ExecutionDenied("Animation changed identity, content, layout or navigation data")

    @staticmethod
    def _render(output: Path, tour: Record) -> None:
        template = (reference_assets() / "viewer.html").read_text()
        payload = json.dumps(tour, ensure_ascii=False).replace("</", "<\\/")
        template, count = re.subn(
            SLOT, lambda m: str(m[1]) + payload + str(m[3]), template, flags=re.S
        )
        if count != 1:
            raise ExecutionDenied("Packaged viewer data slot is unavailable")
        summary = (
            '<aside id="trial-summary">动画全景候选 · 原身份、信息与导航保留。'
            "接缝、对象位置和设备效果待验；补绘不是史实证据。"
            '<a href="../animation-manifest.json">转绘记录</a></aside>'
        )
        template = re.sub(
            r'<aside id="trial-summary">.*?</aside>', lambda _: summary, template, flags=re.S
        )
        (output / "vr_trial/index.html").write_text(template)

    @staticmethod
    def _render_review(source: Path, output: Path, tour: Record) -> None:
        """Render trusted code, importing only source-label metadata from the old review UI."""
        text = (reference_assets() / "review.html").read_text()
        old_review = source / "index.html"
        if old_review.is_file() and old_review.stat().st_size < 2 * 1024 * 1024:
            labels = re.search(
                r'<script id="source-labels" type="application/json">(.*?)</script>',
                old_review.read_text(),
                re.S,
            )
            if labels:
                data = record(json.loads(labels[1]))
                payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
                text = text.replace(
                    "<script>",
                    '<script id="source-labels" type="application/json">'
                    + payload
                    + "</script><script>const sourceLabels=JSON.parse("
                    + 'document.getElementById("source-labels").textContent);',
                    1,
                )
                text = text.replace(
                    "esc(o.historical_id||'未分配来源')",
                    "esc(sourceLabels[o.historical_id]||o.historical_id||'未分配来源')",
                )
                text = text.replace("' · '+esc(s.id)", "' · '+esc(sourceLabels[s.id]||s.id)")
        hotspots = [
            record(h)
            for scene in sequence(tour["scenes"])
            for h in sequence(record(scene)["hotspots"])
            if record(h).get("type") == "info"
        ]
        active = len({string(h["id"]) for h in hotspots})
        summary = (
            f"动画展示候选：{active}项对象、{len(hotspots)}处热点。"
            "身份、来源与人工编辑保留；画质、接缝和位置由用户手工验收。补绘不是史实证据。"
        )
        text = re.sub(
            "当前独立重匹配提案：.*?身份疑点以VR页面说明为准。", lambda _: summary, text, flags=re.S
        )
        text = text.replace("下载当前39项映射表", "下载当前映射快照")
        text = text.replace("${s.image_page+109}", "${s.image_printed_page??'未识别'}")
        text = text.replace("${s.text_page+109}", "${s.text_printed_page??'未识别'}")
        text = text.replace("||1;const $", "||0;const $").replace(
            "))id=1;", "))id=data.objects[0].id;"
        )
        text = re.sub(
            r"已撤下扶手椅→学生房.*?不能视为已拍到的实物。",
            lambda _: "上游身份与证据状态保留，未有效绑定的对象不新增热点。",
            text,
        )
        (output / "index.html").write_text(text)

    @staticmethod
    def _update_report(output: Path, scenes: list[Record], original: str) -> None:
        path = output / "vr_trial/trial_report.json"
        report = record(read_json(path))
        by_id = {string(scene["id"]): scene for scene in scenes}
        parents = {
            string(record(value)["id"]): record(value)
            for value in sequence(record(json.loads(original))["scenes"])
        }
        for value in sequence(report["located"]):
            row = record(value)
            scene = by_id[string(row["scene_id"])]
            data = AnimationWorkflow._image_bytes(string(record(scene["panorama"])["data"]))
            parent = parents[string(scene["id"])]
            parent_data = AnimationWorkflow._image_bytes(string(record(parent["panorama"])["data"]))
            row["parent_panorama_sha256"] = hashlib.sha256(parent_data).hexdigest()
            row["panorama_sha256"] = hashlib.sha256(data).hexdigest()
            row["panorama_revision"] = scene["panoramaRevision"]
            row["state"] = "animation_inherited_angles_pending_visual_review"
            for value2 in sequence(scene["hotspots"]):
                hotspot = record(value2)
                if hotspot.get("id") == f"trial-object-{integer(row['object_id'])}":
                    row["yaw"], row["pitch"] = hotspot["yaw"], hotspot["pitch"]
                    panorama = record(scene["panorama"])
                    row["pixel_center"] = [
                        (float(cast(float, hotspot["yaw"])) + 180)
                        / 360
                        * integer(panorama["width"]),
                        (90 - float(cast(float, hotspot["pitch"])))
                        / 180
                        * integer(panorama["height"]),
                    ]
        write_json(path, report)
