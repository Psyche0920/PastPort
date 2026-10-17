"""Run real-browser acceptance against a fresh synthetic localhost service."""

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path)
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node is required for browser checks")
    with tempfile.TemporaryDirectory(prefix="pastport-browser-") as temporary:
        directory = Path(temporary)
        artifacts = options.artifacts or directory / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = {
            **os.environ,
            "PASTPORT_BROWSER_TOKEN": secrets.token_urlsafe(32),
            "PASTPORT_BROWSER_OUTSIDER": secrets.token_urlsafe(32),
            "PASTPORT_BROWSER_URL": f"http://127.0.0.1:{port}",
            "PASTPORT_BROWSER_ARTIFACTS": str(artifacts.resolve()),
        }
        with (directory / "server.log").open("wb") as logs:
            with subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pastport.development.browser_fixture",
                    "--directory",
                    str(directory / "data"),
                    "--port",
                    str(port),
                ],
                cwd=root,
                env=environment,
                stdout=logs,
                stderr=logs,
            ) as server:
                try:
                    with httpx.Client(timeout=1) as client:
                        for _ in range(100):
                            if server.poll() is not None:
                                raise SystemExit("Synthetic browser service failed to start")
                            try:
                                if (
                                    client.get(
                                        environment["PASTPORT_BROWSER_URL"] + "/api/v1/health"
                                    ).status_code
                                    == 200
                                ):
                                    break
                            except httpx.TransportError:
                                pass
                            time.sleep(0.1)
                        else:
                            raise SystemExit("Synthetic browser service did not become ready")
                    result = subprocess.run(
                        [
                            node,
                            "--test",
                            "--test-timeout=120000",
                            "tests/browser/workbench.test.mjs",
                        ],
                        cwd=root,
                        env=environment,
                        timeout=180,
                        check=False,
                    )
                    if result.returncode:
                        raise SystemExit(result.returncode)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait()
    print("Browser checks passed against fresh synthetic local data.")


if __name__ == "__main__":
    main()
