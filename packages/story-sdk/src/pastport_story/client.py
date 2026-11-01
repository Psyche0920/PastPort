"""Typed Python interface over the existing metered Story authoring use case."""

import fcntl
from contextlib import nullcontext
from pathlib import Path
from typing import Literal

from pastport.adapters.runtime_resources import skill_root
from pastport.adapters.story_materials import StoryMaterialReader
from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.execution_models import ModelProvider
from pastport.domain.common import Contract, Text


class StoryRequest(Contract):
    original_pdf: Path
    source_document: Path
    environment: Path
    media_directory: Path
    output_directory: Path
    brief: Text
    skills_directory: Path | None = None
    revalidate_saved_response: bool = False


class StoryResult(Contract):
    readable_story: Path
    narrative_draft: Path
    validation: Path
    input_lock: Path
    budget: Path
    human_approved: Literal[False] = False


class StoryClient:
    """Generate Story candidates only; never starts gameplay, assembly or publication.

    An injected provider is an explicit local test counterpart under the core's
    test execution policy. Production uses the pinned Codex account transport.
    """

    def __init__(self, provider: ModelProvider | None = None) -> None:
        self.provider = provider

    async def generate(self, request: StoryRequest) -> StoryResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        with (request.output_directory / ".story.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            materials = StoryMaterialReader().read(
                request.original_pdf, request.source_document,
                request.environment, request.media_directory,
            )
            with nullcontext(skill_root()) as bundled:
                skill_directory = request.skills_directory or bundled
                story = await StoryAutomationWorkflow(
                    materials, request.output_directory, skill_directory,
                    request.brief, self.provider,
                    revalidate_saved_response=request.revalidate_saved_response,
                ).run()
        return StoryResult(
            readable_story=story,
            narrative_draft=request.output_directory / "narrative-draft.json",
            validation=request.output_directory / "story-check.json",
            input_lock=request.output_directory / "input-lock.json",
            budget=request.output_directory / "budget.json",
        )
