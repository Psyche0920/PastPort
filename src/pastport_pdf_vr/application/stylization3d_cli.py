"""Bake existing full-sphere artwork into an isolated 3D appearance candidate."""

import argparse
from pathlib import Path

from pastport_pdf_vr.application.stylization3d import Style3DWorkflow
from pastport_pdf_vr.domain.stylization3d import Style3DRun


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    request = Style3DRun.model_validate_json(args.request.read_bytes())
    print(Style3DWorkflow().run(request).model_dump_json())


if __name__ == "__main__":
    main()
