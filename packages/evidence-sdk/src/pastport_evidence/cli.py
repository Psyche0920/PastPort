"""Run the photo-to-document pipeline; no review server or VR command is included."""

from __future__ import annotations

import argparse
from pathlib import Path

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
    parser.add_argument("--no-token-threshold", action="store_true", help="Explicit run-specific token threshold override; original call limit remains")
    args = parser.parse_args()

    from pastport_evidence.adapters.codex_sdk import CodexSDKTransport

    # Pin a new workspace's policy before the usage ledger can make it look legacy.
    from pastport_evidence.application.prompting import resolve_prompt_profile

    resolve_prompt_profile(args.workspace)
    grant = SubscriptionGrant.model_validate_json(args.grant.read_bytes())
    if args.no_token_threshold:
        from pastport_evidence.adapters.execution import SubscriptionExecutor
        SubscriptionExecutor(args.workspace / "codex-executions.sqlite3", grant,
            CodexSDKTransport(grant.effort)).remove_token_threshold("User explicitly authorized continuing this run without the token threshold; preserve call ceilings and usage")
    print(
        "Starting: register inputs -> identify photos -> map historical objects "
        "-> verify evidence -> PDF + IDML",
        flush=True,
    )
    PhotoMappingWorkflow(PopplerPDFReader(), CodexSDKTransport(grant.effort)).run(
        args.pdf, args.photos, args.workspace, grant, args.run_id, args.large_pdf
    )
    result_path = args.workspace / "result.json"
    amendment = args.workspace / "budget-amendment.json"
    if amendment.is_file():
        result_path = args.workspace / f"result-budget-{int(amendment.read_text())}.json"
    if (args.workspace / "candidate-policy.json").is_file():
        revision = int(amendment.read_text()) if amendment.is_file() else None
        result_path = args.workspace / f"result-indexed-{revision}-linked-pdf.json"
    result = OutputPaths.model_validate_json(result_path.read_bytes())
    print(
        f"{result.status}\nPDF: {result.pdf}\nIDML: {result.idml}\n"
        f"Unresolved items: {len(result.gaps)}"
    )


if __name__ == "__main__":
    main()
