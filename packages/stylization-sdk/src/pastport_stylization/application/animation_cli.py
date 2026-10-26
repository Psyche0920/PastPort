"""Subscription-powered labelled-museum animation; no separate paid API fallback."""

import argparse
import shutil
from pathlib import Path

from pastport_matched_environment.domain.animation import ExistingPanorama
from pastport_matched_environment.domain.execution import SubscriptionGrant
from pydantic import TypeAdapter

from pastport_stylization.application.animation import AnimationRun, AnimationWorkflow
from pastport_stylization.application.animation_style import approved_animation_style


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
    style = approved_animation_style(args.workspace if args.resume else None)
    grant = SubscriptionGrant.model_validate_json(args.grant.read_bytes()) if args.grant else None
    if grant is not None:
        from pastport_stylization.adapters.codex_image import CodexImageTransport

    existing = (
        TypeAdapter(tuple[ExistingPanorama, ...]).validate_json(args.reuse_images.read_bytes())
        if args.reuse_images
        else ()
    )
    workflow = AnimationWorkflow(
        Path(ffmpeg) if ffmpeg else None,
        style.reference,
        style.policy,
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
