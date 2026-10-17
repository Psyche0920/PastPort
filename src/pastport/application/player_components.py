"""Bind shared JS preparation components to a trusted runtime package and release."""

from pastport.application.package_loader import RuntimePackageLoader
from pastport.application.player_preparation import PlayerComponentCommand, PlayerComponentResult
from pastport.domain.common import ArtifactRef
from pastport.domain.game import ActionRequest, Effect, GameEvent, PlayerState
from pastport.ports.player_preparation import PlayerComponentProcess


class PlayerComponents:
    """One trusted package binding; clients cannot select a replacement package per operation."""

    def __init__(
        self,
        package_content: bytes,
        expected_reference: ArtifactRef,
        release_id: str,
        loader: RuntimePackageLoader,
        process: PlayerComponentProcess,
    ) -> None:
        self.package = loader.load_bytes(package_content, expected_reference)
        self.reference = expected_reference
        self.release_id = release_id
        self.process = process

    def _execute(
        self,
        operation: str,
        state: PlayerState | None = None,
        action_request: ActionRequest | None = None,
        event: GameEvent | None = None,
        effect: Effect | None = None,
    ) -> PlayerComponentResult:
        # Validate the operation literal and its required fields together.
        command = PlayerComponentCommand.model_validate(
            {
                "operation": operation,
                "package": self.package,
                "reference": self.reference,
                "release_id": self.release_id,
                "state": state,
                "action_request": action_request,
                "event": event,
                "effect": effect,
            }
        )
        return self.process.execute(command)

    def initial_state(self) -> PlayerState:
        return self._execute("initialize").state

    def validate_state(self, state: PlayerState) -> None:
        self._execute("validate_state", state=state)

    def propose_action(self, state: PlayerState, action: ActionRequest) -> PlayerComponentResult:
        return self._execute("propose_action", state=state, action_request=action)

    def match_rules(self, state: PlayerState, event: GameEvent) -> PlayerComponentResult:
        return self._execute("match_rules", state=state, event=event)

    def evaluate_effect(self, state: PlayerState, effect: Effect) -> PlayerComponentResult:
        return self._execute("evaluate_effect", state=state, effect=effect)
