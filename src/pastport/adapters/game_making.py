"""Compose installed SDK entry points; preserve existing museum assets and Story."""

import hashlib
import json
import os
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pastport.adapters.runtime_resources import runtime_root
from pastport.application.models import ServiceError
from pastport.domain.common import Contract, Sha256
from pastport.domain.game_making import GameMakingRequest


class _World(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    root: str


class _Worlds(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    worlds: tuple[_World, ...]


class _UpstreamReceipt(Contract):
    source_document_sha256: Sha256
    source_pdf_sha256: Sha256
    page_count: int
    world_count: int
    style_variant_count: int
    matching_reused: bool = True
    scene_generation_reused: bool = True
    stylization_reused: bool = True
    new_model_calls: int = 0


class SDKGameMakingStages:
    """The assembler remains separate from the two authoring SDKs."""

    def identity(self) -> str:
        names = (
            "pastport",
            "pastport-evidence",
            "pastport-matched-environment",
            "pastport-stylization",
            "pastport-story",
            "pastport-gameplay",
        )
        try:
            versions = {name: version(name) for name in names}
        except PackageNotFoundError as error:
            raise ServiceError(
                "GAME_SDK_MISSING", "Install authoring and game-making extras"
            ) from error
        digest = hashlib.sha256(json.dumps(versions, sort_keys=True).encode())
        root = runtime_root()
        resources = [root / "tools/prepare_presentation.mjs", root / "tools/gameplay_lifecycle.mjs"]
        for directory in ("frontend/game", "gameplay", "tools/game-package", "src/pastport/player"):
            resources.extend(
                path
                for path in (root / directory).rglob("*")
                if path.is_file() and path.suffix in {".mjs", ".js", ".html", ".css"}
            )
        for path in sorted(resources):
            digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
        for path in sorted(Path(__file__).resolve().parents[1].rglob("*.py")):
            digest.update(str(path.relative_to(Path(__file__).resolve().parents[1])).encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _upstream(self, request: GameMakingRequest) -> None:
        from pastport_evidence.domain.pdf import RegisteredPDF
        from pastport_matched_environment.domain.scene3d import MarbleScene
        from pastport_stylization.domain.stylization3d import Style3DVariant

        document = RegisteredPDF.model_validate_json(request.source_document.read_bytes())
        pdf_hash = self._digest(request.original_pdf)
        if pdf_hash != document.source.asset.sha256:
            raise ServiceError("GAME_SOURCE_MISMATCH", "Registered PDF source changed")
        worlds = _Worlds.model_validate_json(
            (request.museum_directory / "data/scene3d-input.json").read_bytes()
        )
        styled = 0
        for world in worlds.worlds:
            base = (request.museum_directory / world.root).resolve()
            if not base.is_relative_to(request.museum_directory.resolve()):
                raise ServiceError("GAME_WORLD_INVALID", "World path escapes museum")
            scene_root = base / "scene3d"
            scene = MarbleScene.model_validate_json((scene_root / "scene.json").read_bytes())
            for name, expected in (
                (scene.splat, scene.splat_sha256),
                (scene.collider, scene.collider_sha256),
                (scene.panorama, scene.panorama_sha256),
            ):
                if self._digest(scene_root / name) != expected:
                    raise ServiceError("GAME_WORLD_CHANGED", "Registered scene resource changed")
            variant_file = scene_root / "style-variant.json"
            if variant_file.exists():
                variant = Style3DVariant.model_validate_json(variant_file.read_bytes())
                if (
                    variant.world_id != scene.scene_id
                    or variant.base_splat_sha256 != scene.splat_sha256
                    or self._digest(scene_root / variant.splat) != variant.splat_sha256
                    or self._digest(scene_root / variant.panorama) != variant.panorama_sha256
                ):
                    raise ServiceError("GAME_STYLE_CHANGED", "Style no longer matches the scene")
                styled += 1
        receipt = _UpstreamReceipt(
            source_document_sha256=self._digest(request.source_document),
            source_pdf_sha256=pdf_hash,
            page_count=document.page_count,
            world_count=len(worlds.worlds),
            style_variant_count=styled,
        )
        (request.output_directory / "upstream-validation.json").write_text(
            receipt.model_dump_json(indent=2)
        )

    async def story(self, request: GameMakingRequest) -> Path:
        from pastport_story import StoryClient, StoryRequest

        self._upstream(request)
        output = request.output_directory / "story"
        if not output.exists():
            shutil.copytree(request.saved_story_run, output)
        result = await StoryClient().generate(
            StoryRequest(
                original_pdf=request.original_pdf,
                source_document=request.source_document,
                environment=request.environment,
                media_directory=request.media_directory,
                output_directory=output,
                brief=request.brief,
                skills_directory=request.skills_directory,
                revalidate_saved_response=True,
            )
        )
        return result.narrative_draft

    def gameplay(self, request: GameMakingRequest) -> Path:
        from pastport_gameplay import GameplayClient, PreparationRequest

        return (
            GameplayClient()
            .prepare(
                PreparationRequest(
                    story_run=request.output_directory / "story",
                    output_directory=request.output_directory / "gameplay",
                )
            )
            .plan_file
        )

    def presentation(self, request: GameMakingRequest) -> Path:
        from pastport_gameplay import GameplayClient, PresentationRequest

        return (
            GameplayClient()
            .present(
                PresentationRequest(
                    story_run=request.output_directory / "story",
                    preparation_directory=request.output_directory / "gameplay",
                    museum_directory=request.museum_directory,
                    output_file=request.output_directory / "presentation/story-input.json",
                )
            )
            .story_input
        )

    def assembly(self, request: GameMakingRequest) -> Path:
        node = shutil.which("node")
        if node is None:
            raise ServiceError("GAME_NODE_MISSING", "Assembly requires Node.js")
        output = request.output_directory / "game-3d"
        try:
            result = subprocess.run(
                [
                    node,
                    str(runtime_root() / "tools/game-package/build-story-package.mjs"),
                    "build",
                    "--input",
                    str(request.output_directory / "presentation/story-input.json"),
                    "--museum",
                    str(request.museum_directory),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env={"PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ServiceError("GAME_ASSEMBLY_FAILED", "Local assembly did not finish") from error
        if result.returncode:
            raise ServiceError("GAME_ASSEMBLY_FAILED", result.stderr[-4000:])
        return output / "manifest.json"
