"""Same-origin shared revision polling, independent of preview ports and broadcasts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from http.server import BaseHTTPRequestHandler
from importlib.resources import files
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from pastport_matched_environment.application.shared_content import SharedContentAuthority


def install_shared_content(handler: type[BaseHTTPRequestHandler], root: Path) -> None:
    method = "do_GET"
    original = cast(Callable[[BaseHTTPRequestHandler], None], getattr(handler, method))
    authority = SharedContentAuthority(root)

    def respond(request: BaseHTTPRequestHandler, body: bytes, mime: str) -> None:
        request.send_response(200)
        request.send_header("Content-Type", mime)
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        request.end_headers()
        request.wfile.write(body)

    def get(request: BaseHTTPRequestHandler) -> None:
        route = urlsplit(request.path).path
        if route == "/api/shared-content-revision":
            try:
                with closing(sqlite3.connect(authority.database, timeout=5)) as db:
                    rows = db.execute(
                        "SELECT p.modern_id,p.version,v.version,p.historical_id,"
                        "p.image_review,p.text_review,p.proposal_state "
                        "FROM pairings p LEFT JOIN vr_display_contents v "
                        "ON v.object_id=p.modern_id "
                        "ORDER BY p.modern_id"
                    ).fetchall()
                revision = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
                eligible = [
                    r[0]
                    for r in rows
                    if r[3]
                    and r[4] != "unsuitable"
                    and r[5] != "unsuitable"
                    and r[6] != "invalid_structural_relation"
                ]
                respond(
                    request,
                    json.dumps({"revision": revision, "eligible": eligible}).encode(),
                    "application/json",
                )
            except (ValueError, OSError, sqlite3.Error):
                request.send_error(503, "Shared content unavailable; no local fallback")
            return
        if route == "/shared_content.js":
            script = files("pastport_matched_environment").joinpath(
                "scene3d_assets/shared_content.js"
            )
            respond(request, script.read_bytes(), "text/javascript; charset=utf-8")
            return
        if route in ("/", "/index.html", "/vr_trial/index.html"):
            path = root / (
                "vr_trial/index.html" if route.startswith("/vr_trial/") else "index.html"
            )
            try:
                html = path.read_text()
                marker = "new window.PastPortPositionEditor(r).initialize();"
                if route.startswith("/vr_trial/") and "window.PastPortSourceHost=r;" not in html:
                    html = html.replace(
                        marker,
                        marker + "window.PastPortSourceHost=r;"
                        "window.dispatchEvent(new Event('pastport-source-ready'));",
                        1,
                    )
                html = html.replace('<script src="/scene3d/shared_content.js"></script>', "")
                html += '\n<script src="/shared_content.js"></script>\n'
                respond(request, html.encode(), "text/html; charset=utf-8")
            except OSError:
                request.send_error(503, "Review page unavailable")
            return
        original(request)

    setattr(handler, method, get)
