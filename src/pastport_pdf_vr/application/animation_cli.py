"""Subscription-powered labelled-museum animation; no separate paid API fallback."""

import argparse
import shutil
from pathlib import Path

from pydantic import TypeAdapter

from pastport_pdf_vr.adapters.codex_image import CodexImageTransport
from pastport_pdf_vr.application.animation import AnimationRun, AnimationWorkflow, digest
from pastport_pdf_vr.application.reference_environment import reference_assets
from pastport_pdf_vr.domain.animation import ExistingPanorama
from pastport_pdf_vr.domain.execution import SubscriptionGrant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--grant", type=Path)
    mode.add_argument(
        "--reuse-images",
        type=Path,
        help="Bound existing panoramas; skips SDK and generation entirely",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None and args.reuse_images is None:
        parser.error("FFmpeg with the v360 filter is required")
    assets = reference_assets().parent / "animation_assets"
    style = assets / "approved-style.png"
    if digest(style) != "bddb6ddc8903b3ce4fdd57d94f1803a001c93f8c68140f965e40f51e31e4198a":
        parser.error("Pinned approved animation style changed")
    grant = SubscriptionGrant.model_validate_json(args.grant.read_bytes()) if args.grant else None
    existing = (
        TypeAdapter(tuple[ExistingPanorama, ...]).validate_json(args.reuse_images.read_bytes())
        if args.reuse_images
        else ()
    )
    workflow = AnimationWorkflow(
        Path(ffmpeg) if ffmpeg else None,
        style,
        assets / "policy-v1.txt",
        CodexImageTransport(grant.effort) if grant else None,
    )
    result = workflow.run(
        AnimationRun(
            source_directory=str(args.environment),
            workspace=str(args.workspace),
            grant=grant,
            existing_panoramas=existing,
            resume=args.resume,
        )
    )
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
