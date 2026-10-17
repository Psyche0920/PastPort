"""Saved player sessions; JS owns gameplay and the repository owns atomic durability."""

from pastport.application.player_runtime import PlayerRuntimeError
from pastport.domain.game import ActionRequest, ActionResult, PlayerState
from pastport.domain.packages import RuntimePackage
from pastport.domain.player_saves import PlayerSaveKey
from pastport.ports.modules import PlayerRuntimePort
from pastport.ports.player_saves import PlayerSaveRepository


class PlayerService:
    def __init__(
        self,
        repository: PlayerSaveRepository,
        runtime: PlayerRuntimePort,
        package: RuntimePackage,
        release_id: str,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.package = package
        self.release_id = release_id

    def create(self, key: PlayerSaveKey) -> PlayerState:
        initial = self.runtime.initial_state(self.package, self.release_id)
        stored = self.repository.create(key, initial)
        self.runtime.validate_state(self.package, stored)
        return stored

    def load(self, key: PlayerSaveKey) -> PlayerState:
        stored = self.repository.load(key)
        if stored is None:
            raise PlayerRuntimeError("SAVE_NOT_FOUND", "Player save was not found")
        if stored.release_id != self.release_id or stored.project_id != self.package.project_id:
            raise PlayerRuntimeError(
                "SAVE_IDENTITY_MISMATCH",
                "Save belongs to another release; choose an explicit new save ID",
            )
        self.runtime.validate_state(self.package, stored)
        return stored

    def apply(self, key: PlayerSaveKey, action: ActionRequest) -> ActionResult:
        # A lost CAS requires one fresh read: retries replay receipts, other stale actions fail.
        for _ in range(2):
            previous = self.load(key)
            result = self.runtime.apply_action(self.package, previous, action)
            if result.state == previous:
                return result
            if self.repository.compare_and_swap(key, previous, result.state):
                return result
        raise PlayerRuntimeError("STATE_STALE", "Player save changed; reload before another action")
