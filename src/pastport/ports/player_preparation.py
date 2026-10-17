"""A typed process boundary; engine rules remain in the shared JavaScript implementation."""

from typing import Protocol

from pastport.application.player_preparation import PlayerComponentCommand, PlayerComponentResult


class PlayerComponentProcess(Protocol):
    def execute(self, command: PlayerComponentCommand) -> PlayerComponentResult: ...
