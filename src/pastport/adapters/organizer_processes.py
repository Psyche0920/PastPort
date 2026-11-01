"""One owned native SDK process group; cancellation never redispatches a paid stage."""

import os
import signal
import subprocess
import sys
import threading

from pastport.application.models import ServiceError


class NativeSDKProcessRunner:
    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._closed = False

    def run(self, module: str, arguments: tuple[str, ...], timeout_seconds: float) -> None:
        if module not in ("pastport_evidence.cli", "pastport_matched_environment.cli"):
            raise ValueError("Native module is not registered")
        with self._mutex:
            if self._closed:
                raise ServiceError(
                    "INPUT_PREPARATION_INTERRUPTED", "输入准备已停止，回执已保留。", 409
                )
            process = subprocess.Popen(
                (sys.executable, "-m", module, *arguments),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._process = process
        try:
            try:
                code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as error:
                self._terminate(process)
                raise ServiceError(
                    "NATIVE_STAGE_TIMEOUT", "原生SDK步骤超时；不会自动再次调用模型。", 409
                ) from error
            if code:
                raise ServiceError(
                    "NATIVE_STAGE_STOPPED", "原生SDK步骤未完成，原始结果和用量记录已保留。", 409
                )
        finally:
            self._terminate(process)
            with self._mutex:
                self._process = None

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        # Descendants can remain after an SDK parent exits; own the complete group.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()

    def close(self) -> None:
        with self._mutex:
            self._closed = True
            process = self._process
        if process is not None:
            self._terminate(process)
