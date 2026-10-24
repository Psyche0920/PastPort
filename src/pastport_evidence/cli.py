"""Run the photo-to-document pipeline; no review server or VR command is included."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from pastport_evidence.adapters.codex_sdk import CodexSDKTransport
from pastport_evidence.adapters.pdf import PopplerPDFReader
from pastport_evidence.application.document_package import OutputPaths
from pastport_evidence.application.photo_mapping import PhotoMappingWorkflow
from pastport_evidence.domain.execution import SubscriptionGrant


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate comparison PDF and editable IDML from photos and a historical PDF"
    )
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument(
        "--grant",
        required=True,
        type=Path,
        help="Explicit finite Codex subscription grant; never a credential",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--large-pdf", action="store_true")
    args = parser.parse_args()
    executable = shutil.which("pdftoppm")
    if executable is None:
        parser.error("Poppler pdftoppm is required (macOS: brew install poppler)")
    grant = SubscriptionGrant.model_validate_json(args.grant.read_bytes())
    print(
        "Starting: register inputs -> identify photos -> map historical objects "
        "-> verify evidence -> PDF + IDML",
        flush=True,
    )
    PhotoMappingWorkflow(PopplerPDFReader(Path(executable)), CodexSDKTransport(grant.effort)).run(
        args.pdf, args.photos, args.workspace, grant, args.run_id, args.large_pdf
    )
    result = OutputPaths.model_validate_json((args.workspace / "result.json").read_bytes())
    print(
        f"{result.status}\nPDF: {result.pdf}\nIDML: {result.idml}\n"
        f"Unresolved items: {len(result.gaps)}"
    )


if __name__ == "__main__":
    main()
