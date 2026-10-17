"""Bounded Node transport for the shared browser/headless preparation components."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import ValidationError

from pastport.application.player_preparation import (
    PlayerComponentCommand,
    PlayerComponentResponse,
    PlayerComponentResult,
    PlayerProcessResponse,
)
from pastport.application.player_runtime import PlayerRuntimeCommand, PlayerRuntimeResponse
from pastport.domain.common import Contract
from pastport.domain.game import ActionResult


class PlayerComponentError(ValueError):
    """Safe operational failure at the player process boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NodePlayerProcess:
    """Execute a fixed local runner, without shell evaluation or inherited provider secrets."""

    def __init__(self, node_path: Path | None = None, timeout_seconds: float = 5.0) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("Player timeout must be between zero and 30 seconds")
        self.node_path = node_path
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = 16 * 1024 * 1024
        self.runner = Path(__file__).resolve().parents[1] / "player" / "runner.mjs"

    def execute(self, command: PlayerComponentCommand) -> PlayerComponentResult:
        return self._execute(command.model_dump_json().encode("utf-8"), PlayerComponentResponse)

    def execute_runtime(self, command: PlayerRuntimeCommand) -> ActionResult:
        return self._execute(command.model_dump_json().encode("utf-8"), PlayerRuntimeResponse)

    def _execute[Result: Contract](
        self, payload: bytes, response_type: type[PlayerProcessResponse[Result]]
    ) -> Result:
        executable = str(self.node_path) if self.node_path else shutil.which("node")
        if executable is None:
            raise PlayerComponentError(
                "PLAYER_NODE_UNAVAILABLE", "Node.js is required for player components"
            )
        if len(payload) > self.maximum_bytes:
            raise PlayerComponentError(
                "PLAYER_INPUT_TOO_LARGE", "Player command exceeds the byte limit"
            )
        # Files avoid unbounded PIPE capture; check output size before reading.
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
            source.write(payload)
            source.seek(0)
            try:
                with subprocess.Popen(
                    [executable, "--max-old-space-size=128", str(self.runner)],
                    stdin=source,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    cwd=self.runner.parent,
                    env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                ) as process:
                    try:
                        return_code = process.wait(timeout=self.timeout_seconds)
                    except subprocess.TimeoutExpired as error:
                        process.kill()
                        process.wait()
                        raise PlayerComponentError(
                            "PLAYER_TIMEOUT", "Player component exceeded its time limit"
                        ) from error
            except OSError as error:
                raise PlayerComponentError(
                    "PLAYER_PROCESS_UNAVAILABLE", "Player component process could not start"
                ) from error
            if output.tell() > self.maximum_bytes:
                raise PlayerComponentError(
                    "PLAYER_OUTPUT_TOO_LARGE", "Player response exceeds the byte limit"
                )
            output.seek(0)
            try:
                response = response_type.model_validate_json(output.read(self.maximum_bytes + 1))
            except ValidationError as error:
                raise PlayerComponentError(
                    "PLAYER_RESPONSE_INVALID", "Player component returned an invalid response"
                ) from error
        if not response.ok:
            assert response.code is not None and response.message is not None
            raise PlayerComponentError(response.code, response.message)
        if return_code != 0 or response.result is None:
            raise PlayerComponentError("PLAYER_PROCESS_FAILED", "Player component did not complete")
        return response.result
