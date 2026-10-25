"""Local entrypoints for preflight, explicitly labeled replay and live review."""

from __future__ import annotations

import argparse
from pathlib import Path

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.api.server import LocalReviewApplication
from pastport_pdf_vr.application.bootstrap import ReplayWorkflow
from pastport_pdf_vr.application.configuration import load_project_config
from pastport_pdf_vr.domain.tour import ImportedTour


def main() -> None:
    parser = argparse.ArgumentParser(prog="pastport-pdf-vr")
    subcommands = parser.add_subparsers(dest="command", required=True)
    environment_build = subcommands.add_parser(
        "environment-build", help="Matched PDF and new VR to the demonstrated review and viewer"
    )
    for name in ("pdf", "tour", "grant", "workspace"):
        environment_build.add_argument("--" + name, type=Path, required=True)
    environment_build.add_argument("--run-id", required=True)
    environment_build.add_argument("--title", default="PastPort · 匹配环境")
    environment_build.add_argument("--large-pdf", action="store_true")
    environment_build.add_argument(
        "--resume-inspection",
        action="store_true",
        help="Reconcile a diagnosed inspection validation error using settled receipts",
    )
    environment_build.add_argument(
        "--resume-validation-stage",
        choices=("matched_pdf", "fresh_localization", "structural_review"),
    )
    prepare_environment = subcommands.add_parser(
        "environment-prepare", help="Prepare fresh PDF/tour images for the environment Agent Skill"
    )
    for name in ("pdf", "tour", "workspace"):
        prepare_environment.add_argument("--" + name, type=Path, required=True)
    prepare_environment.add_argument("--large-pdf", action="store_true")
    render_environment = subcommands.add_parser(
        "environment-render", help="Assemble the Agent's evidence into the exact reference UI"
    )
    for name in ("evidence", "locations", "pdf", "tour", "output"):
        render_environment.add_argument("--" + name, type=Path, required=True)
    render_environment.add_argument("--serve", action="store_true")
    render_environment.add_argument("--port", type=int, default=8795)
    studio = subcommands.add_parser("studio", help="Open browser upload, generation and review")
    studio.add_argument("--workspace", type=Path, default=Path(".runtime/studio"))
    studio.add_argument("--port", type=int, default=8794)
    replay = subcommands.add_parser(
        "replay", help="Import an explicitly supplied demo report; no model inference"
    )
    replay.add_argument("--config", type=Path, required=True)
    replay.add_argument("--tour", type=Path, required=True)
    replay.add_argument("--report", type=Path, required=True)
    replay.add_argument("--workspace", type=Path, required=True)
    replay.add_argument("--run-id", required=True)
    replay.add_argument(
        "--legacy-db", type=Path, help="Optional read-only legacy demo evidence counterpart"
    )
    serve = subcommands.add_parser("serve", help="Serve local linked review and VR")
    serve.add_argument("--workspace", type=Path, required=True)
    serve.add_argument("--port", type=int, default=8794)
    status = subcommands.add_parser(
        "codex-status", help="Check local login/model without inference"
    )
    status.add_argument("--model", default="gpt-6.1-sol")
    execute = subcommands.add_parser(
        "codex-run", help="Execute one typed, grant-bound semantic request"
    )
    execute.add_argument("--kind", choices=("inspect", "associate", "draft"), required=True)
    for name in ("request", "grant", "assets", "workspace", "output"):
        execute.add_argument("--" + name, type=Path, required=True)
    execute.add_argument("--image-bindings", type=Path)
    build = subcommands.add_parser("build", help="PDF + tour to numbered VR and linked review")
    for name in ("pdf", "tour", "grant", "workspace", "run-id"):
        build.add_argument("--" + name, type=str if name == "run-id" else Path, required=True)
    build.add_argument(
        "--mapping-mode", choices=("same_site", "demo_substitution"), default="same_site"
    )
    build.add_argument("--large-pdf", action="store_true", help="Explicit 512 MiB PDF profile")
    build.add_argument(
        "--resume-evidence",
        action="store_true",
        help="Explicitly reconcile a known evidence validation failure using settled cached calls",
    )
    build.add_argument("--pdftoppm", type=Path)
    build.add_argument("--serve", action="store_true", help="Start linked VR/review after building")
    build.add_argument("--port", type=int, default=8794)
    photo_map = subcommands.add_parser(
        "photo-map", help="Create a photo-first substitution mapping PDF"
    )
    for name in ("pdf", "photos", "workspace", "grant", "run-id"):
        photo_map.add_argument("--" + name, type=str if name == "run-id" else Path, required=True)
    photo_map.add_argument("--large-pdf", action="store_true")
    photo_map.add_argument("--pdftoppm", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "environment-build":
        import shutil

        from pastport_pdf_vr.adapters.codex_sdk import CodexSDKTransport
        from pastport_pdf_vr.application.environment_build import EnvironmentBuildWorkflow
        from pastport_pdf_vr.domain.execution import SubscriptionGrant

        binary = shutil.which("pdftoppm")
        if binary is None:
            parser.error("Poppler pdftoppm is required")
        grant = SubscriptionGrant.model_validate_json(arguments.grant.read_bytes())
        summary = EnvironmentBuildWorkflow(Path(binary), CodexSDKTransport(grant.effort)).run(
            arguments.pdf,
            arguments.tour,
            grant,
            arguments.workspace,
            arguments.run_id,
            title=arguments.title,
            large_pdf=arguments.large_pdf,
            resume_inspection=arguments.resume_inspection,
            recovery_stage=arguments.resume_validation_stage,
        )
        print(summary.model_dump_json())
        return
    if arguments.command == "environment-prepare":
        import shutil

        from pastport_pdf_vr.application.environment_agent import EnvironmentAgentPreparation

        binary = shutil.which("pdftoppm")
        if binary is None:
            parser.error("Poppler pdftoppm is required for visual PDF inspection")
        prepared = EnvironmentAgentPreparation(Path(binary)).prepare(
            arguments.pdf,
            arguments.tour,
            arguments.workspace,
            large_pdf=arguments.large_pdf,
        )
        print(f"Prepared {prepared.page_count} pages and {prepared.viewpoint_count} viewpoints")
        print(f"Continue with the repository environment-generation skill: {prepared.manifest}")
        return
    if arguments.command == "environment-render":
        import subprocess
        import sys

        from pastport_pdf_vr.application.reference_environment import (
            CandidateBuilder,
            reference_assets,
        )

        source = arguments.tour / "index.html" if arguments.tour.is_dir() else arguments.tour
        CandidateBuilder(
            reference_assets(),
            arguments.evidence,
            arguments.pdf,
            source,
            arguments.locations,
            arguments.output,
        ).build()
        print(f"Reference-format VR/review candidate: {arguments.output}")
        if arguments.serve:
            subprocess.run(
                [sys.executable, "start_demo.py", "--port", str(arguments.port)],
                cwd=arguments.output,
                check=True,
            )
        return
    if arguments.command == "studio":
        import uvicorn

        from pastport_pdf_vr.api.studio import StudioApplication

        application = StudioApplication(arguments.workspace)
        print(f"Studio: http://127.0.0.1:{arguments.port}/")
        uvicorn.run(application.app, host="127.0.0.1", port=arguments.port, access_log=False)
        return
    if arguments.command == "photo-map":
        import shutil

        from pastport_pdf_vr.adapters.codex_sdk import CodexSDKTransport
        from pastport_pdf_vr.adapters.pdf import PopplerPDFReader
        from pastport_pdf_vr.application.photo_mapping import PhotoMappingWorkflow
        from pastport_pdf_vr.domain.execution import SubscriptionGrant

        binary = str(arguments.pdftoppm) if arguments.pdftoppm else shutil.which("pdftoppm")
        if binary is None:
            parser.error("Poppler pdftoppm is required")
        grant = SubscriptionGrant.model_validate_json(arguments.grant.read_bytes())
        PhotoMappingWorkflow(PopplerPDFReader(Path(binary)), CodexSDKTransport(grant.effort)).run(
            arguments.pdf,
            arguments.photos,
            arguments.workspace,
            grant,
            arguments.run_id,
            arguments.large_pdf,
        )
        print("Photo mapping PDF and structured data are ready in", arguments.workspace)
        return
    if arguments.command == "build":
        import shutil

        from pastport_pdf_vr.adapters.codex_sdk import CodexSDKTransport
        from pastport_pdf_vr.adapters.pdf import PopplerPDFReader
        from pastport_pdf_vr.application.automatic_build import AutomaticBuildWorkflow
        from pastport_pdf_vr.domain.execution import SubscriptionGrant

        binary = str(arguments.pdftoppm) if arguments.pdftoppm else shutil.which("pdftoppm")
        if binary is None:
            parser.error("Poppler pdftoppm is required; install Poppler or supply --pdftoppm")
        grant = SubscriptionGrant.model_validate_json(arguments.grant.read_bytes())
        tour = arguments.tour / "index.html" if arguments.tour.is_dir() else arguments.tour
        results = AutomaticBuildWorkflow(
            PopplerPDFReader(Path(binary)), CodexSDKTransport(grant.effort)
        ).run(
            arguments.pdf,
            tour,
            arguments.workspace,
            grant,
            arguments.run_id,
            arguments.mapping_mode,
            arguments.large_pdf,
            arguments.resume_evidence,
        )
        gaps = sorted({gap for result in results for gap in result.gaps})
        print("Build completed" + (" with gaps" if gaps else ""))
        for gap in gaps:
            print("Gap:", gap)
        print("Start preview with: pastport-pdf-vr serve --workspace", arguments.workspace)
        if arguments.serve:
            _serve_workspace(arguments.workspace, arguments.port)
        return
    if arguments.command == "codex-status":
        from pastport_pdf_vr.adapters.codex_sdk import CodexSDKTransport

        print(CodexSDKTransport().readiness(arguments.model).model_dump_json())
        return
    if arguments.command == "codex-run":
        from pastport_pdf_vr.application.codex_execution import run_codex_request

        run_codex_request(
            arguments.kind,
            arguments.request,
            arguments.grant,
            arguments.assets,
            arguments.workspace,
            arguments.output,
            arguments.image_bindings,
        )
        print("Codex semantic result saved; original review/VR data was not replaced")
        return
    if arguments.command == "replay":
        config = load_project_config(arguments.config)
        if config.input_representation.value != "synthetic_replay":
            parser.error("replay requires input_representation=synthetic_replay")
        results = ReplayWorkflow().run(
            config.project_id,
            arguments.tour,
            arguments.report,
            arguments.workspace,
            config.limits,
            arguments.run_id,
            arguments.legacy_db,
        )
        for result in results:
            print(result.model_dump_json())
    else:
        _serve_workspace(arguments.workspace, arguments.port)


def _serve_workspace(workspace: Path, port: int) -> None:
    import uvicorn

    from pastport_pdf_vr.domain.build import BuildSummary

    tour = ImportedTour.model_validate_json((workspace / "tour.json").read_bytes())
    summary_path = workspace / "build-summary.json"
    summary = (
        BuildSummary.model_validate_json(summary_path.read_bytes())
        if summary_path.exists()
        else None
    )
    application = LocalReviewApplication(
        tour.source.project_id,
        tour,
        SQLiteEditorialRepository(workspace / "editorial.sqlite3"),
        LocalAssetStore(workspace / "assets"),
        summary,
    )
    print(f"Review: http://127.0.0.1:{port}/")
    print(f"VR: http://127.0.0.1:{port}/vr/")
    uvicorn.run(application.app, host="127.0.0.1", port=port, access_log=False)


if __name__ == "__main__":
    main()
