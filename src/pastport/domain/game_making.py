"""Private game-production inputs, with explicit reuse rather than implied generation."""

from pathlib import Path
from typing import Literal

from pastport.domain.common import Contract, Text


class GameMakingRequest(Contract):
    original_pdf: Path
    source_document: Path
    environment: Path
    media_directory: Path
    museum_directory: Path
    saved_story_run: Path
    skills_directory: Path
    brief: Text
    output_directory: Path
    mode: Literal["saved_response_only"] = "saved_response_only"


class GameMakingResult(Contract):
    game_directory: Path
    entry: Literal["/?scene=3d"] = "/?scene=3d"
    new_model_calls: Literal[0] = 0
    historical_approval: Literal[False] = False
    human_play_acceptance: Literal[False] = False
