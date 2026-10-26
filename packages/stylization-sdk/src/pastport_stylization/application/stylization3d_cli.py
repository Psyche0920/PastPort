"""Bake existing full-sphere artwork into an isolated 3D appearance candidate."""

import argparse
import shutil
from pathlib import Path

from pastport_stylization.application.stylization3d import Style3DWorkflow
from pastport_stylization.domain.stylization3d import Style3DRun


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request", type=Path)
    mode.add_argument("--tour-request", type=Path)
    parser.add_argument("--style-reference", type=Path)
    parser.add_argument("--style-policy", type=Path)
    args = parser.parse_args()
    if args.tour_request:
        from pastport_stylization.application.stylization3d_tour import (
            Style3DTourRun,
            Style3DTourWorkflow,
        )

        tour = Style3DTourRun.model_validate_json(args.tour_request.read_bytes())
        animation = None
        if not tour.panoramas:
            from pastport_stylization.adapters.codex_image import CodexImageTransport
            from pastport_stylization.application.animation import AnimationWorkflow

            if tour.grant is None or args.style_reference is None or args.style_policy is None:
                parser.error(
                    "Fresh artwork needs an explicit grant, --style-reference and --style-policy"
                )
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                parser.error("FFmpeg is required")
            animation = AnimationWorkflow(
                Path(ffmpeg),
                args.style_reference.resolve(strict=True),
                args.style_policy.resolve(strict=True),
                CodexImageTransport(tour.grant.effort),
            )
        print(Style3DTourWorkflow(animation=animation).run(tour).model_dump_json())
        return
    request = Style3DRun.model_validate_json(args.request.read_bytes())
    print(Style3DWorkflow().run(request).model_dump_json())


if __name__ == "__main__":
    main()
