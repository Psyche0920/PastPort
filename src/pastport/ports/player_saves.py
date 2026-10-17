"""Atomic player persistence, separate from the authoritative editorial review database."""

from typing import Protocol

from pastport.domain.game import PlayerState
from pastport.domain.player_saves import PlayerSaveKey


class PlayerSaveRepository(Protocol):
    def create(self, key: PlayerSaveKey, state: PlayerState) -> PlayerState: ...
    def load(self, key: PlayerSaveKey) -> PlayerState | None: ...
    def compare_and_swap(
        self, key: PlayerSaveKey, previous: PlayerState, following: PlayerState
    ) -> bool: ...
