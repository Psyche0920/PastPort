"""Typed preparation protocol, separate from committed player actions and saves."""

from typing import Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import ArtifactRef, Contract, Identifier
from pastport.domain.game import ActionRequest, Effect, GameEvent, PlayerState, RuleTrace
from pastport.domain.packages import RuntimePackage


class PlayerComponentCommand(Contract):
    operation: Literal[
        "initialize", "validate_state", "propose_action", "match_rules", "evaluate_effect"
    ]
    package: RuntimePackage
    reference: ArtifactRef
    release_id: Identifier
    state: PlayerState | None = None
    action_request: ActionRequest | None = None
    event: GameEvent | None = None
    effect: Effect | None = None

    @model_validator(mode="after")
    def operation_fields(self) -> Self:
        required = {
            "initialize": set(),
            "validate_state": {"state"},
            "propose_action": {"state", "action_request"},
            "match_rules": {"state", "event"},
            "evaluate_effect": {"state", "effect"},
        }[self.operation]
        present = {
            name
            for name in ("state", "action_request", "event", "effect")
            if getattr(self, name) is not None
        }
        if present != required:
            raise ValueError("Command fields must match the preparation operation")
        return self


class PlayerComponentResult(Contract):
    status: Literal["prepared"] = "prepared"
    committed: Literal[False] = False
    state: PlayerState
    emitted_events: tuple[GameEvent, ...] = ()
    feedback_keys: tuple[Identifier, ...] = ()
    matched_rules: tuple[RuleTrace, ...] = ()


class PlayerProcessResponse[Result: Contract](Contract):
    ok: bool
    result: Result | None = None
    code: Identifier | None = None
    message: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def result_or_error(self) -> Self:
        if self.ok:
            if self.result is None or self.code is not None or self.message is not None:
                raise ValueError("Successful component responses require only a result")
        elif self.result is not None or self.code is None or self.message is None:
            raise ValueError("Failed component responses require only a safe error")
        return self


class PlayerComponentResponse(PlayerProcessResponse[PlayerComponentResult]):
    pass


class PlayerInitialStateResponse(Contract):
    status: Literal["prepared"] = "prepared"
    committed: Literal[False] = False
    can_commit_actions: Literal[True] = True
    can_persist: Literal[True] = True
    state: PlayerState
