"""Own isolated local reference servers, loading only packaged runtime code."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import types
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from pastport_pdf_vr.application.reference_environment import reference_assets


@dataclass(frozen=True, slots=True)
class PreviewProcess:
    process: asyncio.subprocess.Process
    port: int


class ReferencePreviewPool:
    """One server per immutable generation run; close all owned processes on shutdown."""

    def __init__(self) -> None:
        self._processes: dict[Path, PreviewProcess] = {}
        self._lock = asyncio.Lock()

    async def ensure(self, root: Path) -> int:
        root = root.resolve()
        async with self._lock:
            existing = self._processes.get(root)
            if existing and existing.process.returncode is None:
                return existing.port
            if not (root / "pastport_matching.sqlite3").is_file():
                raise ValueError("The reference result is not initialized")
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pastport_pdf_vr.application.reference_preview",
                "--root",
                str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                if process.stdout is None:
                    raise RuntimeError("Preview startup channel unavailable")
                line = await asyncio.wait_for(process.stdout.readline(), 15)
                payload: object = json.loads(line)
                if not isinstance(payload, dict) or type(payload.get("port")) is not int:
                    raise ValueError("Preview did not return a bound local port")
                port = cast(int, payload["port"])
                if not 1024 <= port <= 65535:
                    raise ValueError("Invalid preview port")
            except BaseException:
                await self._stop(process)
                raise
            self._processes[root] = PreviewProcess(process, port)
            return port

    @staticmethod
    async def _stop(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()

    async def close(self) -> None:
        async with self._lock:
            for child in self._processes.values():
                await self._stop(child.process)
            self._processes.clear()


def serve(root: Path, port: int = 0) -> None:
    """Reuse trusted shipped services; never execute Python from a generated directory."""
    root = root.resolve()
    if not (root / "pastport_matching.sqlite3").is_file():
        raise ValueError("Missing initialized reference database")
    modules: dict[str, types.ModuleType] = {}
    for name in ("vr_content", "vr_positions", "review_server"):
        module = types.ModuleType(name)
        # Runtime resources locate data relative to __file__, while code comes only
        # from the installed package's fixed, audited templates.
        module.__file__ = str(root / (name + ".py"))
        sys.modules[name] = module
        source = reference_assets() / (name + ".py.template")
        exec(compile(source.read_text(), str(source), "exec"), module.__dict__)
        modules[name] = module
    module = modules["review_server"]
    handler = cast(type[BaseHTTPRequestHandler], module.ReviewHandler)
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        if (root / "scene3d/attachment.json").is_file():
            from pastport_pdf_vr.api.scene3d import install_routes

            install_routes(handler, root, server.server_port)
        module.__dict__["PORT"] = server.server_port
        print(json.dumps({"port": server.server_port}), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    serve(parser.parse_args().root)
