"""Injectable production boundary; web/application layers never import SDK facades."""

from pathlib import Path
from typing import Protocol, TypeVar

from pastport.domain.common import Contract
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import OrganizerStart


class OrganizerProduction(Protocol):
    def validate(self, request: GameMakingRequest) -> None: ...
    async def run(
        self,
        request: GameMakingRequest,
        start: OrganizerStart,
        output: Path,
        *,
        resume: bool = False,
    ) -> None: ...


Record = TypeVar("Record", bound=Contract)


class OrganizerRepository(Protocol):
    @property
    def directory(self) -> Path: ...
    def get(self, kind: str, key: str, model: type[Record]) -> Record: ...
    def list(self, kind: str, model: type[Record]) -> tuple[Record, ...]: ...
    def save(self, kind: str, key: str, value: Contract) -> None: ...
