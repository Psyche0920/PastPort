"""Bake existing full-sphere artwork into an isolated 3D appearance candidate."""

import argparse
from pathlib import Path

from pastport_pdf_vr.application.stylization3d import Style3DWorkflow
from pastport_pdf_vr.domain.stylization3d import Style3DRun


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request", type=Path)
    mode.add_argument("--tour-request", type=Path)
    args = parser.parse_args()
    if args.tour_request:
        from pastport_pdf_vr.application.stylization3d_tour import (
            Style3DTourRun,
            Style3DTourWorkflow,
        )

        tour = Style3DTourRun.model_validate_json(args.tour_request.read_bytes())
        print(Style3DTourWorkflow().run(tour).model_dump_json())
        return
    request = Style3DRun.model_validate_json(args.request.read_bytes())
    print(Style3DWorkflow().run(request).model_dump_json())


if __name__ == "__main__":
    main()
