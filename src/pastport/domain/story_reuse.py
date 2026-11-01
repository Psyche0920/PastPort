"""Provider-free compatibility evidence; retained narrative is never a fresh generation."""

from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field

from pastport.domain.common import Contract, Identifier, Sha256, Text


class StoryIntroductionChange(Contract):
    task_id: Identifier
    object_number: int = Field(ge=1)
    before: str | None
    after: str | None


class StoryReuseConfirmation(Contract):
    report_sha256: Sha256
    confirm_unchanged_story: Literal[True]


class StoryReuseDecision(Contract):
    actor_id: Identifier
    decided_at: AwareDatetime
    report_sha256: Sha256
    environment_sha256: Sha256
    parent_draft_sha256: Sha256
    introduction_changes: tuple[StoryIntroductionChange, ...]
    scope: Literal["private_reuse_only"] = "private_reuse_only"


class StoryReuseReport(Contract):
    compatibility_version: int = Field(default=0, ge=0, le=1)
    introduction_changes: tuple[StoryIntroductionChange, ...] = ()
    confirmation: StoryReuseDecision | None = None
    status: Literal["compatible", "incompatible", "missing", "needs_confirmation"]
    issues: tuple[Text, ...]
    parent_story_run: Path | None = None
    parent_draft_sha256: Sha256 | None = None
    environment_sha256: Sha256 | None = None
    source_index_sha256: Sha256 | None = None
    capability_catalog_sha256: Sha256 | None = None
    new_model_calls: Literal[0] = 0
