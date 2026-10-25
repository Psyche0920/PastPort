"""Apply the existing panorama-animation output to an isolated real 3D asset."""

from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from importlib.resources import files
from pathlib import Path
from typing import Literal, Protocol

from PIL import Image

from pastport_pdf_vr.adapters.spz_style import SpzAppearanceBaker
from pastport_pdf_vr.application.animation import digest
from pastport_pdf_vr.application.reference_environment import read_json, record, string
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.domain.scene3d import MarbleScene, SceneRenderVariant
from pastport_pdf_vr.domain.stylization3d import (
    SplatBakeStats,
    Style3DDelivery,
    Style3DRun,
    Style3DVariant,
    StyleCamera,
)


class AppearanceBaker(Protocol):
    def bake(
        self,
        source: Path,
        target: Path,
        original: Path,
        painted: Path,
        camera: StyleCamera,
        scale: float,
        ground: float,
        strength: float,
    ) -> SplatBakeStats: ...


def current_style(root: Path) -> Style3DVariant | None:
    path = root / "scene3d/style-variant.json"
    if not path.is_file():
        return None
    variant = Style3DVariant.model_validate_json(path.read_bytes())
    attachment = record(read_json(root / "scene3d/attachment.json"))
    scene = MarbleScene.model_validate(attachment["scene"])
    if variant.scene_binding != attachment["binding"] or variant.world_id != scene.scene_id:
        raise ValueError("Styled asset belongs to another scene")
    folder = root / "scene3d"
    if (
        digest(folder / variant.splat) != variant.splat_sha256
        or digest(folder / variant.base_splat) != variant.base_splat_sha256
        or digest(folder / variant.panorama) != variant.panorama_sha256
    ):
        raise ValueError("Styled asset bytes changed")
    return variant


class Style3DWorkflow:
    """Reuse painted imagery, preserving independent scene geometry and review edits."""

    def __init__(self, baker: AppearanceBaker | None = None) -> None:
        self.baker = baker or SpzAppearanceBaker()

    def run(self, request: Style3DRun) -> Style3DDelivery:
        source = Path(request.source_directory).resolve(strict=True)
        workspace = Path(request.workspace).resolve()
        if (
            workspace == source
            or workspace.is_relative_to(source)
            or source.is_relative_to(workspace)
        ):
            raise ValueError("Use an isolated workspace outside the source result")
        workspace.parent.mkdir(parents=True, exist_ok=True)
        with (workspace.parent / f".{workspace.name}.style3d.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                return self._run(source, workspace, request)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _run(self, source: Path, workspace: Path, request: Style3DRun) -> Style3DDelivery:
        receipt = workspace / "request.json"
        encoded = request.model_copy(update={"resume": False}).model_dump_json()
        if workspace.exists():
            if not request.resume or not receipt.is_file() or receipt.read_text() != encoded:
                raise ValueError("Workspace already exists; never rebuild its review database")
            delivery = Style3DDelivery.model_validate_json(
                (workspace / "delivery.json").read_bytes()
            )
            if current_style(Path(delivery.environment)) is None:
                raise ValueError("Completed style receipt is missing")
            return delivery
        attachment = record(read_json(source / "scene3d/attachment.json"))
        scene = MarbleScene.model_validate(attachment["scene"])
        selected = string(attachment["source_scene_id"])
        original_name = string(attachment["source_panorama"])
        if original_name not in ("source-panorama.jpg", "source-panorama.png"):
            raise ValueError("Unexpected source panorama path")
        original = source / "scene3d" / original_name
        image = request.panorama
        painted = Path(image.image_path).resolve(strict=True)
        if image.scene_id != selected or digest(original) != image.source_panorama_sha256:
            raise ValueError("Painted panorama is bound to another source viewpoint")
        if painted.stat().st_size > 64 * 1024**2 or digest(painted) != image.image_sha256:
            raise ValueError("Painted panorama hash/size changed")
        with Image.open(original) as photo, Image.open(painted) as art:
            if photo.size != art.size or art.width != art.height * 2:
                raise ValueError("Retain original full-sphere dimensions without upscaling")
        base_name: Literal["scene.spz", "scene-full.spz"] = "scene.spz"
        base_hash = scene.splat_sha256
        variant_path = source / "scene3d/render-variant.json"
        if variant_path.is_file():
            render = SceneRenderVariant.model_validate_json(variant_path.read_bytes())
            if render.scene_binding != attachment["binding"] or render.world_id != scene.scene_id:
                raise ValueError("Full-resolution variant belongs to another scene")
            base_name, base_hash = render.splat, render.splat_sha256
        if digest(source / "scene3d" / base_name) != base_hash:
            raise ValueError("Source SPZ hash changed")
        paths = list(source.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise ValueError("Source result cannot contain symbolic links")
        if sum(p.stat().st_size for p in paths if p.is_file()) > 2 * 1024**3:
            raise ValueError("Source result exceeds 2 GiB")
        workspace.mkdir()
        atomic_write(receipt, encoded)
        output = workspace / "result"
        shutil.copytree(
            source,
            output,
            ignore=shutil.ignore_patterns(
                "*.sqlite3", "*-wal", "*-shm", "style-variant.json", "scene-styled.spz"
            ),
        )
        with closing(
            sqlite3.connect(f"{(source / 'pastport_matching.sqlite3').as_uri()}?mode=ro", uri=True)
        ) as src:
            with closing(sqlite3.connect(output / "pastport_matching.sqlite3")) as dst:
                src.backup(dst)
        with closing(sqlite3.connect(output / "pastport_matching.sqlite3")) as db:
            row = db.execute(
                "SELECT version,payload_json FROM scene3d_alignment WHERE id=1"
            ).fetchone()
        raw_camera = record(json.loads(row[1]))
        raw_camera["version"] = row[0]
        camera = StyleCamera.model_validate(raw_camera)
        if not camera.confirmed and camera.version == 0 and not camera.editor:
            camera = camera.model_copy(
                update={
                    "origin": camera.origin.model_copy(
                        update={"x": 0.0, "y": scene.ground_plane_offset, "z": 0.0}
                    )
                }
            )
        # User requested automatic continuation; estimates remain explicitly unconfirmed.
        folder = output / "scene3d"
        with Image.open(painted) as art:
            art.convert("RGB").save(folder / "style-panorama.png")
        stats = self.baker.bake(
            folder / base_name,
            folder / "scene-styled.spz",
            folder / original_name,
            folder / "style-panorama.png",
            camera,
            scene.metric_scale_factor,
            scene.ground_plane_offset,
            request.strength,
        )
        assets = files("pastport_pdf_vr").joinpath("scene3d_assets")
        for asset in assets.iterdir():
            if asset.is_file():
                (folder / asset.name).write_bytes(asset.read_bytes())
        (output / "navigation_boundary.js").write_bytes(
            assets.joinpath("navigation_boundary.js").read_bytes()
        )
        reference = files("pastport_pdf_vr").joinpath("animation_assets/approved-style.png")
        style_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
        provenance = Path(image.provenance_ref)
        if provenance.is_file():
            style_hash = string(record(read_json(provenance)).get("style_sha256", style_hash))
        variant = Style3DVariant(
            scene_binding=string(attachment["binding"]),
            world_id=scene.scene_id,
            source_scene_id=selected,
            base_splat=base_name,
            base_splat_sha256=base_hash,
            splat_sha256=digest(folder / "scene-styled.spz"),
            panorama_sha256=digest(folder / "style-panorama.png"),
            source_panorama_sha256=image.source_panorama_sha256,
            style_reference_sha256=style_hash,
            render_mode=request.render_mode,
            provenance_ref=image.provenance_ref,
            camera=camera,
            alignment_kind="human_alignment" if camera.confirmed else "automatic_estimate",
            stats=stats,
        )
        atomic_write(folder / "style-variant.json", variant.model_dump_json(indent=2))
        archive = Path(shutil.make_archive(str(workspace / "styled-scene"), "zip", output))
        delivery = Style3DDelivery(
            environment=str(output),
            archive=str(archive),
            manifest=str(folder / "style-variant.json"),
            source_scene_id=selected,
        )
        atomic_write(workspace / "delivery.json", delivery.model_dump_json(indent=2))
        return delivery
