"""Format-independent job orchestration over the supported native VR/3D contracts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Literal

from pastport_pdf_vr.adapters.codex_image import CodexImageTransport
from pastport_pdf_vr.application.animation import SLOT, AnimationRun, AnimationWorkflow, digest
from pastport_pdf_vr.application.animation_style import approved_animation_style
from pastport_pdf_vr.application.reference_environment import record, sequence
from pastport_pdf_vr.application.stylization3d_tour import (
    Style3DTourRun,
    Style3DTourWorkflow,
    TourPackageImporter,
)
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.models import DomainModel


class StyleInput(DomainModel):
    kind: Literal["panorama", "scene3d"]
    source: str
    viewpoints: int
    required_calls: int
    source_sha256: str


class AutomaticStyleRun(DomainModel):
    source: StyleInput
    workspace: str
    grant: SubscriptionGrant
    resume: bool = False


class AutomaticStyleDelivery(DomainModel):
    kind: Literal["panorama", "scene3d"]
    archive: str
    environment: str | None = None
    tour_delivery: str | None = None
    acceptance: str = "pending_user_acceptance"
    agent_report: str | None = None
    model_review: Literal["model_review_pass", "needs_human_review"] | None = None


def inspect_input(archive: Path, workspace: Path) -> StyleInput:
    target = workspace / "input"
    TourPackageImporter().extract(archive, target, 4 * 1024**3)
    tours = list(target.rglob("tour.json"))
    valid_tours = [p for p in tours if p.stat().st_size < 2 * 1024**2]
    if len(valid_tours) == 1:
        count = preflight_3d(valid_tours[0].parent, valid_tours[0])
        if valid_tours[0].parent != target:
            normalized = workspace / "native-tour.zip"
            shutil.make_archive(str(normalized.with_suffix("")), "zip", valid_tours[0].parent)
            archive = normalized
        return StyleInput(
            kind="scene3d",
            source=str(archive),
            viewpoints=count,
            required_calls=count * 6,
            source_sha256=digest(archive),
        )
    environments = [
        p.parent
        for p in target.rglob("import-manifest.json")
        if (p.parent / "pastport_matching.sqlite3").is_file()
        and (p.parent / "vr_trial/index.html").is_file()
    ]
    if len(environments) != 1:
        raise ValueError(
            "Upload one complete labelled VR export or native 3D tour ZIP. "
            "Standalone meshes, vendor runtimes and screenshots need an adapter."
        )
    source = environments[0]
    if (source / "shared-content.json").exists():
        raise ValueError(
            "Export a portable review snapshot; live authority bindings are not accepted "
            "by this VR upload adapter. The uploaded files have been retained."
        )
    html = (source / "vr_trial/index.html").read_text()
    match = re.search(SLOT, html, re.S)
    if match is None:
        raise ValueError("No schema-4 panorama payload")
    tour_data = record(json.loads(match[2]))
    if tour_data.get("schemaVersion") != 4:
        raise ValueError("Unsupported panorama format")
    import base64
    import io

    from PIL import Image

    for value in sequence(tour_data["scenes"]):
        scene = record(value)
        pano = record(scene["panorama"])
        raw = base64.b64decode(str(pano["data"]).split(",", 1)[1], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width != image.height * 2 or image.width > 4096:
                raise ValueError("Current artwork path supports native 2:1 spheres up to 4096x2048")
    count = len(sequence(tour_data["scenes"]))
    if not 1 <= count <= 16:
        raise ValueError("This one-grant workflow supports 1 to 16 viewpoints")
    return StyleInput(
        kind="panorama",
        source=str(source),
        viewpoints=count,
        required_calls=count * 6,
        source_sha256=digest(archive),
    )


def animation_workflow(
    grant: SubscriptionGrant, workspace: Path | None = None
) -> AnimationWorkflow:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("FFmpeg with v360 support is required before starting")
    style = approved_animation_style(workspace)
    return AnimationWorkflow(
        Path(ffmpeg), style.reference, style.policy, CodexImageTransport(grant.effort)
    )


def run(
    request: AutomaticStyleRun, *, workflow: AnimationWorkflow | None = None
) -> AutomaticStyleDelivery:
    if request.source.required_calls > request.grant.max_calls:
        raise ValueError("Grant cannot cover six image turns for every viewpoint; not started")
    image_workspace = (
        Path(request.workspace) / "animation"
        if request.source.kind == "scene3d"
        else Path(request.workspace)
    )
    workflow = workflow or animation_workflow(
        request.grant, image_workspace if request.resume else None
    )
    if request.source.kind == "scene3d":
        source = Path(request.source.source)
        if digest(source) != request.source.source_sha256:
            raise ValueError("Source archive changed")
        value = Style3DTourWorkflow(animation=workflow).run(
            Style3DTourRun(
                source_archive=str(source),
                workspace=request.workspace,
                panoramas=(),
                grant=request.grant,
                resume=request.resume,
            )
        )
        return AutomaticStyleDelivery(
            kind="scene3d",
            archive=value.archive,
            tour_delivery=str(Path(request.workspace) / "delivery.json"),
        )
    value2 = workflow.run(
        AnimationRun(
            source_directory=request.source.source,
            workspace=request.workspace,
            grant=request.grant,
            resume=request.resume,
        )
    )
    return AutomaticStyleDelivery(
        kind="panorama", archive=value2.archive, environment=value2.environment
    )


def preflight_3d(incoming: Path, tour_path: Path) -> int:
    import gzip
    import struct
    import zipfile

    from PIL import Image

    from pastport_pdf_vr.application.scene3d_tour import TourManifest

    tour = TourManifest.model_validate_json(tour_path.read_bytes())
    if not 1 <= len(tour.views) <= 16:
        raise ValueError("One bounded job supports 1 to 16 viewpoints")
    ids = {view.source_scene_id for view in tour.views}
    for view in tour.views:
        package = incoming / view.package
        if (
            package.resolve().parent != (incoming / "views").resolve()
            or digest(package) != view.sha256
        ):
            raise ValueError("View package path or checksum changed")
        with zipfile.ZipFile(package) as bundle:
            for name in ("scene/attachment.json", "source-tour.json"):
                if bundle.getinfo(name).file_size > 100 * 1024**2:
                    raise ValueError("Oversized source metadata")
            attachment = json.loads(bundle.read("scene/attachment.json"))
            if attachment["source_scene_id"] != view.source_scene_id:
                raise ValueError("3D source viewpoint binding differs")
            original = attachment["source_panorama"]
            if original not in ("source-panorama.jpg", "source-panorama.png"):
                raise ValueError("Invalid original panorama reference")
            with bundle.open("scene/" + original) as stream, Image.open(stream) as image:
                if image.width != image.height * 2 or image.width > 4096:
                    raise ValueError(
                        "Current native artwork path requires full 2:1 panoramas up to 4096x2048"
                    )
            source_tour = json.loads(bundle.read("source-tour.json"))
            if (
                source_tour.get("schemaVersion") != 4
                or {s["id"] for s in source_tour["scenes"]} != ids
            ):
                raise ValueError(
                    "The complete package must cover exactly its original tour viewpoints"
                )
            splat = "scene.spz"
            if "scene/render-variant.json" in bundle.namelist():
                variant = json.loads(bundle.read("scene/render-variant.json"))
                if variant["scene_binding"] != attachment["binding"]:
                    raise ValueError("Full-resolution asset binding differs")
                splat = variant["splat"]
            if splat not in ("scene.spz", "scene-full.spz"):
                raise ValueError("Invalid render asset path")
            if bundle.getinfo("scene/" + splat).file_size > 256 * 1024**2:
                raise ValueError("3D render asset exceeds 256 MiB")
            with bundle.open("scene/" + splat) as stream, gzip.GzipFile(fileobj=stream) as zipped:
                magic, version, count, degree, bits, flags, reserved = struct.unpack(
                    "<III4B", zipped.read(16)
                )
            if (
                magic != 0x5053474E
                or version != 2
                or degree != 0
                or flags & ~1
                or reserved
                or not 1 <= count <= 3000000
            ):
                raise ValueError("This path supports SPZ v2/SH0; no generation has started")
    return len(tour.views)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    request = AutomaticStyleRun.model_validate_json(args.request.read_bytes())
    result = run(request)
    Path(request.workspace).parent.joinpath("automatic-delivery.json").write_text(
        result.model_dump_json(indent=2)
    )
    print(result.model_dump_json(), flush=True)
