"""One source-bound tour package in, one styled independent-world tour package out."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import stat
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from pydantic import Field

from pastport_pdf_vr.application.animation import SLOT, digest
from pastport_pdf_vr.application.reference_environment import reference_assets
from pastport_pdf_vr.application.scene3d_tour import TourManifest, TourSource, export_tour
from pastport_pdf_vr.application.shared_content import SharedContentAuthority
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.application.stylization3d import Style3DWorkflow
from pastport_pdf_vr.domain.animation import ExistingPanorama
from pastport_pdf_vr.domain.models import DomainModel
from pastport_pdf_vr.domain.stylization3d import Style3DDelivery, Style3DRun


class Style3DTourRun(DomainModel):
    source_archive: str
    workspace: str
    panoramas: tuple[ExistingPanorama, ...] = Field(min_length=1, max_length=50)
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
        (result / "index.html").write_bytes((reference_assets() / "review.html").read_bytes())
        for name in ("review_server", "vr_content", "vr_positions", "start_demo"):
            shutil.copy2(reference_assets() / f"{name}.py.template", result / f"{name}.py")


class Style3DTourWorkflow:
    """Keep one tour-level semantic authority and independent per-view spatial snapshots."""

    def run(self, request: Style3DTourRun) -> Style3DTourDelivery:
        source = Path(request.source_archive).resolve(strict=True)
        workspace = Path(request.workspace).resolve()
        payload = request.model_copy(update={"resume": False}).model_dump_json()
        if workspace.exists():
            if (
                not request.resume
                or (workspace / "request.json").read_text() != payload
                or (workspace / "source.sha256").read_text() != digest(source)
            ):
                raise ValueError("Existing tour workspace is bound to different input")
            return Style3DTourDelivery.model_validate_json(
                (workspace / "delivery.json").read_bytes()
            )
        workspace.mkdir(parents=True)
        atomic_write(workspace / "request.json", payload)
        atomic_write(workspace / "source.sha256", digest(source))
        importer = TourPackageImporter()
        incoming = workspace / "input"
        importer.extract(source, incoming, 4 * 1024**3)
        tour = TourManifest.model_validate_json((incoming / "tour.json").read_bytes())
        images = {image.scene_id: image for image in request.panoramas}
        if len(images) != len(request.panoramas) or set(images) != {
            v.source_scene_id for v in tour.views
        }:
            raise ValueError("Painted panorama bindings must cover the exact source tour")
        roots: list[tuple[int, str, Path]] = []
        for view in tour.views:
            path = incoming / view.package
            if (
                path.resolve().parent != (incoming / "views").resolve()
                or digest(path) != view.sha256
            ):
                raise ValueError("View package binding changed")
            folder = workspace / "imported" / f"point-{view.number}"
            importer.scene(path, folder)
            roots.append((view.number, view.source_scene_id, folder / "result"))
        authority = workspace / "content"
        authority.mkdir()
        first = roots[0][2]
        shutil.copy2(first / "import-manifest.json", authority / "import-manifest.json")
        with closing(sqlite3.connect(first / "pastport_matching.sqlite3")) as src:
            with closing(sqlite3.connect(authority / "pastport_matching.sqlite3")) as dst:
                src.backup(dst)
        # Linear legacy edits are merged only into this isolated tour snapshot, never the source.
        for _, _, root in roots:
            SharedContentAuthority(root).bind(authority)
        views: list[StyledTourView] = []
        for number, scene_id, root in roots:
            delivery = Style3DWorkflow().run(
                Style3DRun(
                    source_directory=str(root),
                    workspace=str(workspace / "views" / f"point-{number}"),
                    panorama=images[scene_id],
                )
            )
            preview_id = hashlib.sha256(scene_id.encode()).hexdigest()[:32]
            views.append(
                StyledTourView(
                    number=number,
                    source_scene_id=scene_id,
                    preview_id=preview_id,
                    delivery=delivery,
                )
            )
        archive = workspace / "styled-tour.zip"
        export_tour(
            tuple(
                TourSource(v.number, v.source_scene_id, Path(v.delivery.environment)) for v in views
            ),
            archive,
        )
        result = Style3DTourDelivery(
            archive=str(archive), content_authority=str(authority), views=tuple(views)
        )
        atomic_write(workspace / "delivery.json", result.model_dump_json(indent=2))
        return result
