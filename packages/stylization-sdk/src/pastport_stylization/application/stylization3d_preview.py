"""Serve one isolated styled tour with the existing review/3D runtime."""

from __future__ import annotations

import argparse
import json
import select
import shutil
import sqlite3
import subprocess
import sys
from contextlib import ExitStack, closing
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from pastport_stylization.application.stylization3d_tour import Style3DTourDelivery


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.stdout is not None:
        process.stdout.close()


def serve(delivery_path: Path, port: int = 0) -> None:
    delivery = Style3DTourDelivery.model_validate_json(delivery_path.read_bytes())
    child_ports: dict[str, int] = {}
    ids = {v.source_scene_id: v.preview_id for v in delivery.views}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                links = "".join(
                    f'<a href="/scene3d-results/{escape(v.preview_id, quote=True)}/" '
                    f'target="tour-viewport">Viewpoint {v.number}</a>'
                    for v in delivery.views
                )
                template = files("pastport_stylization").joinpath("web/styled-tour-preview.html")
                first_view = escape(delivery.views[0].preview_id, quote=True)
                body = (
                    template.read_text()
                    .replace("<!--VIEWPOINT_LINKS-->", links)
                    .replace("<!--INITIAL_VIEW-->", f"/scene3d-results/{first_view}/")
                    .encode()
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/studio.css":
                body = files("pastport_matched_environment").joinpath("web/studio.css").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/download":
                archive = Path(delivery.archive)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="styled-tour.zip"')
                self.send_header("Content-Length", str(archive.stat().st_size))
                self.end_headers()
                with archive.open("rb") as source:
                    shutil.copyfileobj(source, self.wfile, 65536)
                return
            key = parsed.path.removeprefix("/scene3d-results/").strip("/")
            if parsed.path.startswith("/scene3d-results/") and key in child_ports:
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"http://127.0.0.1:{child_ports[key]}/scene3d/index.html"
                    + ("?" + parsed.query if parsed.query else ""),
                )
                self.end_headers()
                return
            self.send_error(404)

    with ExitStack() as stack:
        server = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", port), Handler))
        portal = f"http://127.0.0.1:{server.server_port}"
        for view in delivery.views:
            root = Path(view.delivery.environment)

            def redirect(arrow: dict[str, object]) -> None:
                target = ids.get(str(arrow.get("target_scene_id")))
                if target:
                    query = urlsplit(str(arrow.get("target_url", ""))).query
                    arrow["target_url"] = f"{portal}/scene3d-results/{target}/" + (
                        "?" + query if query else ""
                    )

            with closing(sqlite3.connect(root / "pastport_matching.sqlite3")) as db, db:
                for binding, hot, payload in db.execute(
                    "SELECT binding,hotspot_id,payload FROM scene3d_arrows"
                ).fetchall():
                    arrow = json.loads(payload)
                    redirect(arrow)
                    db.execute(
                        "UPDATE scene3d_arrows SET payload=? WHERE binding=? AND hotspot_id=?",
                        (json.dumps(arrow), binding, hot),
                    )
            seed = root / "scene3d/arrow-seed.json"
            if seed.is_file():
                data = json.loads(seed.read_text())
                for arrow in data["transitions"]:
                    redirect(arrow)
                seed.write_text(json.dumps(data))
            (root / "scene3d/portal-navigation.json").write_text(
                json.dumps({"endpoint": f"{portal}/api/scene3d-navigation/{view.preview_id}"})
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pastport_matched_environment.application.reference_preview",
                    "--root",
                    str(root),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            stack.callback(stop, process)
            if process.stdout is None or not select.select([process.stdout], [], [], 15)[0]:
                raise RuntimeError("Isolated preview did not report a bound local port")
            value = json.loads(process.stdout.readline())
            child_ports[view.preview_id] = int(value["port"])
        print(json.dumps({"url": portal}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    options = parser.parse_args()
    serve(options.delivery, options.port)
