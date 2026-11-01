"""Compatibility creates a new immutable input without rewriting its parent story."""

from pathlib import Path
from typing import Protocol

from pastport.domain.game_making import GameMakingRequest
from pastport.domain.story_reuse import StoryReuseDecision


class StoryReusePort(Protocol):
    def prepare(
        self,
        previous: GameMakingRequest,
        current: GameMakingRequest,
        output: Path,
        *,
        decision: StoryReuseDecision | None = None,
    ) -> GameMakingRequest: ...
