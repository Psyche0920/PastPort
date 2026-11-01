"""Own loopback-only player previews; Organizer does not rewrite player code."""

import asyncio
import os
import secrets
import shutil
import signal
import socket
from pathlib import Path
from urllib.parse import urlencode

from pastport.adapters.runtime_resources import runtime_root
from pastport.application.models import ServiceError


class OrganizerPreviewPool:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._processes: dict[Path, tuple[asyncio.subprocess.Process, str]] = {}

    async def ensure(self, directory: Path) -> str:
        root = directory.resolve(strict=True)
        async with self._lock:
            existing = self._processes.get(root)
            if existing is not None and existing[0].returncode is None:
                return existing[1]
            if len(self._processes) >= 2:
                oldest = next(iter(self._processes))
                process, _ = self._processes.pop(oldest)
                await self._close_process(process)
            node = shutil.which("node")
            if node is None:
                raise ServiceError("GAME_NODE_MISSING", "玩家预览需要 Node.js。", 503)
            token = secrets.token_urlsafe(32)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(128)
                port = listener.getsockname()[1]
                environment = {
                    "PATH": os.environ.get("PATH", os.defpath),
                    "PASTPORT_PORT": str(port),
                    "PASTPORT_LISTEN_FD": str(listener.fileno()),
                    "PASTPORT_LOCAL_DEMO": str(root),
                    "PASTPORT_HOST_ROOT": str(root),
                    "PASTPORT_PREVIEW_TOKEN": token,
                    "PASTPORT_PREVIEW_COOKIE": "pastport_preview_" + str(port),
                }
                process = await asyncio.create_subprocess_exec(
                    node,
                    str(runtime_root() / "tools/game-package/serve3d.mjs"),
                    env=environment,
                    pass_fds=(listener.fileno(),),
                    start_new_session=True,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            try:
                if process.stdout is None:
                    raise ServiceError("PREVIEW_START_FAILED", "玩家预览未启动。", 503)
                line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
                if not line.startswith(b"Story 3D integration:"):
                    raise ServiceError("PREVIEW_START_FAILED", "玩家预览未启动。", 503)
            except (OSError, TimeoutError, ServiceError):
                await self._close_process(process)
                raise
            url = f"http://127.0.0.1:{port}/?" + urlencode({"scene": "3d", "preview_token": token})
            self._processes[root] = (process, url)
            return url

    @staticmethod
    async def _close_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    async def close(self) -> None:
        for process, _ in self._processes.values():
            await self._close_process(process)
        self._processes.clear()
