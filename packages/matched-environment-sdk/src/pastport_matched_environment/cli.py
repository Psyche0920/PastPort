"""Matched PDF and fresh panorama generation entrypoints."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="pastport-matched-environment")
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
    tour_preview = subcommands.add_parser(
        "tour-preview", help="Run registered independent 3D views with shared navigation"
    )
    tour_preview.add_argument("--environment", type=Path, required=True)
    tour_preview.add_argument("--view", type=Path, action="append", required=True)
    tour_preview.add_argument("--port", type=int, default=8797)
    status = subcommands.add_parser(
        "codex-status", help="Check local login/model without inference"
    )
    status.add_argument("--model", default="gpt-6.1-sol")
    attach = subcommands.add_parser(
        "scene3d-attach", help="Attach an existing Marble world to a matched environment"
    )
    for name in ("environment", "world", "workspace"):
        attach.add_argument("--" + name, type=Path, required=True)
    attach.add_argument("--source-scene", default="")
    generate3d = subcommands.add_parser(
        "scene3d-generate", help="Generate once from a matched panorama, then attach its records"
    )
    for name in ("environment", "workspace"):
        generate3d.add_argument("--" + name, type=Path, required=True)
    generate3d.add_argument("--source-scene", default="")
    generate3d.add_argument(
        "--model", choices=("marble-1.1", "marble-1.0-draft"), default="marble-1.1"
    )
    generate3d.add_argument("--credit-budget", type=int, required=True)
    generate3d.add_argument("--authorize-marble", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "tour-preview":
        import uvicorn

        from pastport_matched_environment.api.tour_preview import (
            TourPreviewApplication,
            TourPreviewView,
        )

        if not 1024 <= arguments.port <= 65535:
            parser.error("Use a local port from 1024 to 65535")
        tour_application = TourPreviewApplication(
            arguments.environment,
            tuple(TourPreviewView.from_result(path) for path in arguments.view),
            f"http://127.0.0.1:{arguments.port}",
        )
        uvicorn.run(tour_application.app, host="127.0.0.1", port=arguments.port)
        return
    if arguments.command == "scene3d-generate":
        from pastport_matched_environment.application.marble_generation import MarbleGeneration

        print(
            MarbleGeneration().run(
                arguments.environment,
                arguments.workspace,
                arguments.source_scene,
                arguments.model,
                arguments.credit_budget,
                arguments.authorize_marble,
            )
        )
        return
    if arguments.command == "scene3d-attach":
        from pastport_matched_environment.application.scene3d import Scene3DAttachment

        delivery = Scene3DAttachment(
            arguments.environment, arguments.world, arguments.workspace, arguments.source_scene
        ).run()
        print(delivery.model_dump_json())
        return
    if arguments.command == "environment-build":
        import shutil

        from pastport_matched_environment.adapters.codex_sdk import CodexSDKTransport
        from pastport_matched_environment.application.environment_build import (
            EnvironmentBuildWorkflow,
        )
        from pastport_matched_environment.domain.execution import SubscriptionGrant

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

        from pastport_matched_environment.application.environment_agent import (
            EnvironmentAgentPreparation,
        )

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

        from pastport_matched_environment.application.reference_environment import (
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

        from pastport_matched_environment.api.studio import StudioApplication

        application = StudioApplication(arguments.workspace)
        print(f"Studio: http://127.0.0.1:{arguments.port}/")
        uvicorn.run(application.app, host="127.0.0.1", port=arguments.port, access_log=False)
        return
    if arguments.command == "codex-status":
        from pastport_matched_environment.adapters.codex_sdk import CodexSDKTransport

        print(CodexSDKTransport().readiness(arguments.model).model_dump_json())
        return


if __name__ == "__main__":
    main()
