"""Trusted shared-JS runtime contracts and the implementation of PlayerRuntimePort."""

from typing import Literal, Protocol

from pastport.application.package_loader import RuntimePackageLoader
from pastport.application.player_components import PlayerComponents
from pastport.application.player_preparation import PlayerProcessResponse
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract, Identifier
from pastport.domain.game import ActionRequest, ActionResult, PlayerState
from pastport.domain.packages import RuntimePackage
from pastport.ports.player_preparation import PlayerComponentProcess


class PlayerRuntimeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PlayerRuntimeCommand(Contract):
    operation: Literal["apply_action"] = "apply_action"
    package: RuntimePackage
    reference: ArtifactRef
    release_id: Identifier
    state: PlayerState
    action_request: ActionRequest


class PlayerRuntimeResponse(PlayerProcessResponse[ActionResult]):
    pass


class PlayerRuntimeProcess(PlayerComponentProcess, Protocol):
    def execute_runtime(self, command: PlayerRuntimeCommand) -> ActionResult: ...


class SharedPlayerRuntime:
    """Bind an externally trusted package reference; never derive trust from caller payloads."""

    def __init__(
        self,
        content: bytes,
        reference: ArtifactRef,
        release_id: str,
        loader: RuntimePackageLoader,
        process: PlayerRuntimeProcess,
    ) -> None:
        self.components = PlayerComponents(content, reference, release_id, loader, process)
        self.process = process
        self.package = self.components.package
        self.reference = reference
        self.release_id = release_id

    def _check_binding(self, package: RuntimePackage, release_id: str) -> None:
        if (
            release_id != self.release_id
            or CanonicalSerializer.digest(package) != self.reference.sha256
        ):
            raise PlayerRuntimeError(
                "PLAYER_IDENTITY_MISMATCH", "Runtime binding differs from the package or release"
            )

    def initial_state(self, package: RuntimePackage, release_id: str) -> PlayerState:
        self._check_binding(package, release_id)
        return self.components.initial_state()

    def validate_state(self, package: RuntimePackage, state: PlayerState) -> None:
        self._check_binding(package, state.release_id)
        self.components.validate_state(state)

    def apply_action(
        self, package: RuntimePackage, state: PlayerState, action: ActionRequest
    ) -> ActionResult:
        self._check_binding(package, state.release_id)
        return self.process.execute_runtime(
            PlayerRuntimeCommand(
                package=package,
                reference=self.reference,
                release_id=self.release_id,
                state=state,
                action_request=action,
            )
        )
