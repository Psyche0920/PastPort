"""Installed local production stages over the single shared gameplay host."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from pastport.adapters.runtime_resources import runtime_root, skill_root
from pastport.application.models import ServiceError
from pastport.domain.common import Contract
from pastport.domain.gameplay_preparation import GameplayPlan


class PreparationRequest(Contract):
    story_run: Path
    output_directory: Path


class PreparationResult(Contract):
    plan_file: Path
    canonical_environment: Path
    plan: GameplayPlan


class PresentationRequest(Contract):
    story_run: Path
    preparation_directory: Path
    museum_directory: Path
    output_file: Path


class PresentationResult(Contract):
    story_input: Path


class InvestigationRequest(Contract):
    story_input: Path
    museum_directory: Path
    output_directory: Path
    blueprint_file: Path | None = None
    asset_directory: Path | None = None


class InvestigationResult(Contract):
    game_directory: Path
    receipt_file: Path


class GameplayClient:
    """Compile existing Story requirements; never call models."""

    @staticmethod
    def _run(command: list[str], timeout: int) -> None:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout,
                check=False, cwd=runtime_root(),
                env={"PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ServiceError(
                "GAMEPLAY_STAGE_FAILED", "Local gameplay stage did not finish"
            ) from error
        if result.returncode:
            raise ServiceError(
                "GAMEPLAY_STAGE_FAILED", result.stderr[-4000:] or "Local gameplay stage failed"
            )

    def prepare(self, request: PreparationRequest) -> PreparationResult:
        self._run([
            sys.executable, "-I", "-m", "pastport.gameplay_cli",
            "--story-run", str(request.story_run.resolve()),
            "--guidance", str(skill_root() / "gameplay-preparation/SKILL.md"),
            "--output", str(request.output_directory.resolve()),
            "--host", "pastport.demo.activities/1",
        ], 60)
        directory = request.output_directory.resolve()
        plan_file = directory / "gameplay-plan.json"
        return PreparationResult(
            plan_file=plan_file, canonical_environment=directory / "environment-canonical.json",
            plan=GameplayPlan.model_validate_json(plan_file.read_bytes()),
        )

    def present(self, request: PresentationRequest) -> PresentationResult:
        node = shutil.which("node")
        if node is None:
            raise ServiceError("GAMEPLAY_NODE_MISSING", "Presentation requires Node.js")
        output = request.output_file.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run([
            node, str(runtime_root() / "tools/prepare_presentation.mjs"),
            str(request.story_run.resolve() / "narrative-draft.json"),
            str(request.preparation_directory.resolve() / "gameplay-plan.json"),
            str(request.preparation_directory.resolve() / "environment-canonical.json"),
            str(request.museum_directory.resolve()), str(output),
        ], 30)
        return PresentationResult(story_input=output)

    def investigate(self, request: InvestigationRequest) -> InvestigationResult:
        """Validate an explicit blueprint and assemble a new local game, without models."""
        node = shutil.which("node")
        if node is None:
            raise ServiceError("GAMEPLAY_NODE_MISSING", "Investigation requires Node.js")
        output = request.output_directory.resolve()
        command = [
            node, str(runtime_root() / "tools/game-package/build-story-package.mjs"),
            "from-investigation", "--input", str(request.story_input.resolve()),
            "--museum", str(request.museum_directory.resolve()),
            "--output", str(output),
        ]
        if request.blueprint_file is not None:
            command.extend(["--blueprint", str(request.blueprint_file.resolve())])
        if request.asset_directory is not None:
            command.extend(["--activity-assets", str(request.asset_directory.resolve())])
        self._run(command, 180)
        return InvestigationResult(
            game_directory=output, receipt_file=output / "data/investigation-receipt.json",
        )
