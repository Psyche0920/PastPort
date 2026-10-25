"""One source-bound tour package in, one styled independent-world tour package out."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import sqlite3
import stat
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field

from pastport_pdf_vr.application.animation import SLOT, AnimationRun, AnimationWorkflow, digest
from pastport_pdf_vr.application.reference_environment import reference_assets
from pastport_pdf_vr.application.scene3d_tour import TourManifest, TourSource, export_tour
from pastport_pdf_vr.application.shared_content import SharedContentAuthority
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.application.stylization3d import Style3DWorkflow
from pastport_pdf_vr.domain.animation import ExistingPanorama
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.models import DomainModel
from pastport_pdf_vr.domain.stylization3d import Style3DDelivery, Style3DRun


class Style3DTourRun(DomainModel):
    source_archive: str
    workspace: str
    panoramas: tuple[ExistingPanorama, ...] = Field(default=(), max_length=50)
    grant: SubscriptionGrant | None = None
    render_mode: Literal["gaussian", "projective_surface"] = "gaussian"
    resume: bool = False


class StyledTourView(DomainModel):
    number: int
    source_scene_id: str
    preview_id: str
    delivery: Style3DDelivery


class Style3DTourDelivery(DomainModel):
    schema_version: str = "pastport.styled-tour/1.0"
    archive: str
    content_authority: str
    views: tuple[StyledTourView, ...]
    new_model_calls: int = 0
    acceptance: str = "pending_user_acceptance"


class TourPackageImporter:
    """Read only defined native data/assets; never execute uploaded HTML or Python."""

    def extract(self, archive: Path, output: Path, maximum: int) -> None:
        if archive.stat().st_size > maximum:
            raise ValueError("Tour package exceeds its size limit")
        with zipfile.ZipFile(archive) as bundle:
            total = 0
            names: set[str] = set()
            entries = bundle.infolist()
            if len(entries) > 10000:
                raise ValueError("Too many package entries")
            for item in entries:
                path = PurePosixPath(item.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in item.filename
                    or item.filename in names
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise ValueError("Unsafe or duplicate package entry")
                names.add(item.filename)
                total += item.file_size
                if total > maximum or (
                    item.file_size > 1024**2 and item.file_size > max(item.compress_size, 1) * 300
                ):
                    raise ValueError("Expanded package exceeds its bounds")
                if item.is_dir():
                    continue
                destination = output.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target, 65536)

    def scene(self, package: Path, folder: Path) -> None:
        extracted = folder / "data"
        self.extract(package, extracted, 2 * 1024**3)
        if not (extracted / "scene/attachment.json").is_file():
            raise ValueError("This older developer package lacks source bindings; export it again")
        result = folder / "result"
        result.mkdir()
        allowed = {"source.pdf", "mapping-demo.pdf", "import-manifest.json"}
        for item in extracted.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(extracted)
            if rel.parts[0] == "scene":
                # Runtime code is always installed from the current trusted package below.
                if item.suffix not in (".spz", ".glb", ".jpg", ".png", ".json"):
                    continue
                target = result / "scene3d" / Path(*rel.parts[1:])
            elif rel.parts[0] == "media":
                if item.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                    continue
                target = result / rel
            elif rel.as_posix() in allowed:
                target = result / rel
            elif rel.as_posix() == "review.sqlite3":
                target = result / "pastport_matching.sqlite3"
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        tour_raw = (extracted / "source-tour.json").read_text()
        tour = json.loads(tour_raw)
        if tour.get("schemaVersion") != 4:
            raise ValueError("Expected the original schema-4 tour data")
        template = (reference_assets() / "viewer.html").read_text()
        # Escape HTML termination without changing the parsed JSON values.
        encoded = json.dumps(tour, ensure_ascii=False).replace("<", "\\u003c")

        def replace_payload(match: re.Match[str]) -> str:
            return match[1] + encoded + match[3]

        rendered, replacements = re.subn(SLOT, replace_payload, template, flags=re.S)
        if replacements != 1:
            raise ValueError("Trusted viewer template has no unique data slot")
        (result / "vr_trial").mkdir()
        (result / "vr_trial/index.html").write_text(rendered)
        located = []
        for scene in tour["scenes"]:
            for hotspot in scene["hotspots"]:
                if hotspot.get("type") == "info" and str(hotspot.get("id", "")).startswith(
                    "trial-object-"
                ):
                    located.append(
                        {
                            "scene_id": scene["id"],
                            "object_id": int(str(hotspot["id"]).removeprefix("trial-object-")),
                            "yaw": hotspot["yaw"],
                            "pitch": hotspot["pitch"],
                        }
                    )
        (result / "vr_trial/trial_report.json").write_text(json.dumps({"located": located}))
        (result / "index.html").write_bytes((reference_assets() / "review.html").read_bytes())
        for name in ("review_server", "vr_content", "vr_positions", "start_demo"):
            shutil.copy2(reference_assets() / f"{name}.py.template", result / f"{name}.py")


class PreparedStyleView(DomainModel):
    number: int
    scene_id: str
    root: str


class PreparedStyleTour(DomainModel):
    authority: str
    views: tuple[PreparedStyleView, ...]


class Style3DTourWorkflow:
    """One bounded artwork stage followed by free, resumable local asset processing."""

    def __init__(self, animation: AnimationWorkflow | None = None) -> None:
        self.animation = animation

    def run(self, request: Style3DTourRun) -> Style3DTourDelivery:
        import fcntl

        workspace = Path(request.workspace).resolve()
        workspace.parent.mkdir(parents=True, exist_ok=True)
        with (workspace.parent / f".{workspace.name}.tour.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                return self._run(request, workspace)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _run(self, request: Style3DTourRun, workspace: Path) -> Style3DTourDelivery:
        source = Path(request.source_archive).resolve(strict=True)
        payload = request.model_copy(update={"resume": False}).model_dump_json()
        if workspace.exists():
            if (
                not request.resume
                or Style3DTourRun.model_validate_json(
                    (workspace / "request.json").read_bytes()
                ).model_copy(update={"resume": False})
                != request.model_copy(update={"resume": False})
                or (workspace / "source.sha256").read_text() != digest(source)
            ):
                raise ValueError("Existing tour workspace is bound to different input")
            if (workspace / "delivery.json").is_file():
                delivery = Style3DTourDelivery.model_validate_json(
                    (workspace / "delivery.json").read_bytes()
                )
                for completed_view in delivery.views:
                    from pastport_pdf_vr.application.stylization3d import current_style

                    if current_style(Path(completed_view.delivery.environment)) is None:
                        raise ValueError("Completed appearance receipt is missing")
                return delivery
            if not (workspace / "prepared.json").is_file():
                raise ValueError(
                    "Input preparation incomplete; artifacts retained, no provider retry"
                )
        else:
            workspace.mkdir()
            atomic_write(workspace / "request.json", payload)
            atomic_write(workspace / "source.sha256", digest(source))
            self._prepare(source, workspace)
        prepared = PreparedStyleTour.model_validate_json((workspace / "prepared.json").read_bytes())
        images = {image.scene_id: image for image in request.panoramas}
        expected = {v.scene_id for v in prepared.views}
        if request.panoramas and (len(images) != len(request.panoramas) or set(images) != expected):
            raise ValueError("Artwork bindings must cover exactly the complete source tour")
        generation_calls = 0
        if not images:
            images, generation_calls = self._animate(request, workspace, prepared)
        if set(images) != expected:
            raise ValueError("Animated viewpoints differ from the source tour")
        views: list[StyledTourView] = []
        for prepared_view in prepared.views:
            target = workspace / "views" / f"point-{prepared_view.number}"
            view_delivery = Style3DWorkflow().run(
                Style3DRun(
                    source_directory=prepared_view.root,
                    workspace=str(target),
                    panorama=images[prepared_view.scene_id],
                    resume=target.exists(),
                    render_mode=request.render_mode,
                )
            )
            views.append(
                StyledTourView(
                    number=prepared_view.number,
                    source_scene_id=prepared_view.scene_id,
                    preview_id=hashlib.sha256(prepared_view.scene_id.encode()).hexdigest()[:32],
                    delivery=view_delivery,
                )
            )
        archive = workspace / "styled-tour.zip"
        from uuid import uuid4

        pending = workspace / f"packaging-{uuid4().hex}.zip"
        export_tour(
            tuple(
                TourSource(v.number, v.source_scene_id, Path(v.delivery.environment)) for v in views
            ),
            pending,
        )
        pending.replace(archive)
        result = Style3DTourDelivery(
            archive=str(archive),
            content_authority=prepared.authority,
            views=tuple(views),
            new_model_calls=generation_calls,
        )
        atomic_write(workspace / "delivery.json", result.model_dump_json(indent=2))
        return result

    @staticmethod
    def _prepare(source: Path, workspace: Path) -> None:
        importer = TourPackageImporter()
        incoming = workspace / "input"
        importer.extract(source, incoming, 4 * 1024**3)
        tour = TourManifest.model_validate_json((incoming / "tour.json").read_bytes())
        views: list[PreparedStyleView] = []
        for view in tour.views:
            path = incoming / view.package
            if (
                path.resolve().parent != (incoming / "views").resolve()
                or digest(path) != view.sha256
            ):
                raise ValueError("View package binding changed")
            folder = workspace / "imported" / f"point-{view.number}"
            importer.scene(path, folder)
            views.append(
                PreparedStyleView(
                    number=view.number, scene_id=view.source_scene_id, root=str(folder / "result")
                )
            )
        if not views:
            raise ValueError("Tour has no viewpoints")
        authority = workspace / "content"
        authority.mkdir()
        first = Path(views[0].root)
        shutil.copy2(first / "import-manifest.json", authority / "import-manifest.json")
        with closing(sqlite3.connect(first / "pastport_matching.sqlite3")) as src:
            with closing(sqlite3.connect(authority / "pastport_matching.sqlite3")) as dst:
                src.backup(dst)
        for prepared_view in views:
            SharedContentAuthority(Path(prepared_view.root)).bind(authority)
        prepared = PreparedStyleTour(authority=str(authority), views=tuple(views))
        atomic_write(workspace / "prepared.json", prepared.model_dump_json(indent=2))

    def _animate(
        self, request: Style3DTourRun, workspace: Path, prepared: PreparedStyleTour
    ) -> tuple[dict[str, ExistingPanorama], int]:
        from pastport_pdf_vr.application.animation import AnimationDelivery

        if self.animation is None or request.grant is None:
            raise ValueError("New artwork requires an explicit subscription grant and provider")
        saved = workspace / "animation-delivery.json"
        if saved.is_file():
            maps = AnimationDelivery.model_validate_json(saved.read_bytes())
        else:
            image_workspace = workspace / "animation"
            maps = self.animation.run(
                AnimationRun(
                    source_directory=prepared.views[0].root,
                    workspace=str(image_workspace),
                    grant=request.grant,
                    resume=(image_workspace / "run-binding.json").is_file(),
                )
            )
            atomic_write(saved, maps.model_dump_json(indent=2))
        manifest = json.loads(Path(maps.manifest).read_text())
        provenance = {v["scene_id"]: v for v in manifest["views"]}
        html = (Path(maps.environment) / "vr_trial/index.html").read_text()
        match = re.search(SLOT, html, re.S)
        if match is None:
            raise ValueError("Generated artwork payload is missing")
        generated = json.loads(match[2])
        artwork = workspace / "painted"
        artwork.mkdir(exist_ok=True)
        images: dict[str, ExistingPanorama] = {}
        for scene in generated["scenes"]:
            raw = base64.b64decode(scene["panorama"]["data"].split(",", 1)[1], validate=True)
            binding = provenance[scene["id"]]
            if hashlib.sha256(raw).hexdigest() != binding["output_sha256"]:
                raise ValueError("Completed artwork bytes do not match their receipt")
            path = artwork / (hashlib.sha256(str(scene["id"]).encode()).hexdigest() + ".jpg")
            if path.exists() and digest(path) != binding["output_sha256"]:
                raise ValueError("Existing artwork changed; it will not be overwritten")
            if not path.exists():
                path.write_bytes(raw)
            images[scene["id"]] = ExistingPanorama(
                scene_id=scene["id"],
                source_panorama_sha256=binding["source_sha256"],
                image_path=str(path),
                image_sha256=binding["output_sha256"],
                provenance_ref=maps.manifest,
            )
        calls = int(manifest["new_model_calls"])
        return images, calls
