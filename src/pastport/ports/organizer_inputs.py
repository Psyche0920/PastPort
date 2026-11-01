"""Injected native SDK preparation; the controller cannot invent handoff data."""

from pathlib import Path
from typing import Protocol

from pastport.domain.organizer_inputs import NativeInputRequest, NativePreparedInputs


class OrganizerInputPreparer(Protocol):
    def prepare(self, request: NativeInputRequest, output: Path) -> NativePreparedInputs: ...
    def model_calls(self, output: Path) -> int | None: ...
    def close(self) -> None: ...
