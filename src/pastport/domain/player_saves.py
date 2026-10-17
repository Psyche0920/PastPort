"""Player save ownership and immutable persistence identities."""

from typing import Literal

from pastport.domain.common import Contract, Environment, Identifier
from pastport.domain.game import ActionResult, PlayerState


class PlayerSaveKey(Contract):
    environment: Environment
    actor_id: Identifier
    project_id: Identifier
    save_id: Identifier


class CreatePlayerSave(Contract):
    save_id: Identifier


class PlayerSaveView(Contract):
    save_id: Identifier
    persisted: Literal[True] = True
    state: PlayerState


class SavedActionResult(Contract):
    save_id: Identifier
    persisted: Literal[True] = True
    result: ActionResult
