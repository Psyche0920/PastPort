"""One owned native SDK process group; cancellation never redispatches a paid stage."""

import os
import signal
import subprocess
import sqlite3
from contextlib import closing
from pathlib import Path
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
                reason = self._failure_reason(arguments)
                if reason is not None:
                    raise ServiceError(*reason, 409)
                raise ServiceError(
                    "NATIVE_STAGE_STOPPED", "原生SDK步骤未完成，原始结果和用量记录已保留。", 409
                )
        finally:
            self._terminate(process)
            with self._mutex:
                self._process = None

    @staticmethod
    def _failure_reason(arguments: tuple[str, ...]) -> tuple[str, str] | None:
        if "--workspace" not in arguments:
            return None
        index = arguments.index("--workspace") + 1
        if index >= len(arguments):
            return None
        path = Path(arguments[index]) / "codex-executions.sqlite3"
        if not path.is_file():
            return None
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                row = db.execute(
                    "SELECT f.failure_code FROM execution_failures f JOIN executions e "
                    "USING(project,grant_ref,binding) WHERE e.state='recovery_required' LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return None
        reasons = {
            "transport_timeout": ("NATIVE_MODEL_TIMEOUT", "本批模型调用超时，已停止；用量待核对，不自动重试。"),
            "incomplete_response": ("NATIVE_MODEL_INCOMPLETE", "本批模型未返回完整结果，已停止；保留回执，不自动重试。"),
            "usage_missing": ("NATIVE_USAGE_MISSING", "模型未返回用量回执，已停止；核对用量后才能恢复。"),
            "sdk_error": ("NATIVE_MODEL_CONNECTION", "模型SDK执行异常，已停止；详细错误类别已留档，不自动重试。"),
        }
        return reasons.get(row[0]) if row else None

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
