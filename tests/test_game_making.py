"""Main stage recovery must not repeat Story or accept stale inputs/resources."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from pastport.application.game_making import GameMakingWorkflow
from pastport.application.models import ServiceError
from pastport.domain.game_making import GameMakingRequest


class Stages:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_gameplay = True

    def identity(self) -> str:
        return "a" * 64

    def write(self, request: GameMakingRequest, stage: str) -> Path:
        self.calls.append(stage)
        path = request.output_directory / (stage + ".json")
        path.write_text('{}')
        return path

    async def story(self, request: GameMakingRequest) -> Path:
        return self.write(request, "story")

    def gameplay(self, request: GameMakingRequest) -> Path:
        if self.fail_gameplay:
            self.calls.append("gameplay_failed")
            self.fail_gameplay = False
            raise ServiceError("TEST_STOP", "Local stage stopped")
        return self.write(request, "gameplay")

    def presentation(self, request: GameMakingRequest) -> Path:
        return self.write(request, "presentation")

    def assembly(self, request: GameMakingRequest) -> Path:
        self.calls.append("assembly")
        directory = request.output_directory / "game-3d"
        directory.mkdir()
        file = directory / "app.mjs"
        file.write_text('// test host')
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({'files': [{
            'path': 'app.mjs', 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
            'size_bytes': file.stat().st_size,
        }]}))
        return manifest


def request_at(root: Path) -> GameMakingRequest:
    for name in ('pdf', 'document', 'environment', 'saved/input-lock.json',
                 'saved/narrative-draft.json', 'skills/narrative/SKILL.md',
                 'museum/data/presentation.json', 'museum/data/runtime.json',
                 'museum/data/scene3d-input.json'):
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('{}')
    return GameMakingRequest(
        original_pdf=root / 'pdf', source_document=root / 'document',
        environment=root / 'environment', media_directory=root / 'media',
        museum_directory=root / 'museum', saved_story_run=root / 'saved',
        skills_directory=root / 'skills', brief='Private integration',
        output_directory=root / 'output',
    )


def test_resume_skips_completed_story_and_detects_changed_bundle(tmp_path: Path) -> None:
    request = request_at(tmp_path)
    stages = Stages()
    workflow = GameMakingWorkflow(stages)
    with pytest.raises(ServiceError, match='Local stage stopped'):
        asyncio.run(workflow.run(request))
    assert stages.calls == ['story', 'gameplay_failed']
    result = asyncio.run(workflow.run(request))
    assert result.new_model_calls == 0
    assert stages.calls == ['story', 'gameplay_failed', 'gameplay', 'presentation', 'assembly']
    asyncio.run(workflow.run(request))
    assert stages.calls.count('story') == 1
    (result.game_directory / 'app.mjs').write_text('// changed')
    with pytest.raises(ServiceError, match='integrity'):
        asyncio.run(workflow.run(request))


def test_changed_input_cannot_reuse_saved_stage(tmp_path: Path) -> None:
    request = request_at(tmp_path)
    stages = Stages()
    stages.fail_gameplay = False
    workflow = GameMakingWorkflow(stages)
    asyncio.run(workflow.run(request))
    request.environment.write_text('changed')
    with pytest.raises(ServiceError, match='changed inputs'):
        asyncio.run(workflow.run(request))
    assert stages.calls.count('story') == 1
