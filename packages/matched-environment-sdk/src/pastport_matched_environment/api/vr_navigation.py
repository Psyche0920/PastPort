"""Local-only navigation editing routes layered over the trusted review handler."""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from pastport_matched_environment.application.navigation import NavigationEdit, NavigationStore


class NavigationHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        raise NotImplementedError

    def do_POST(self) -> None:
        raise NotImplementedError


def install_navigation(handler: type[BaseHTTPRequestHandler], root: Path, port: int) -> None:
    store = NavigationStore(root)
    target = cast(type[NavigationHandler], handler)
    original_get, original_post = target.do_GET, target.do_POST

    def respond(request: BaseHTTPRequestHandler, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        request.send_response(status)
        request.send_header("Content-Type", "application/json; charset=utf-8")
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        request.end_headers()
        request.wfile.write(body)

    def get(request: BaseHTTPRequestHandler) -> None:
        if urlsplit(request.path).path != "/api/vr-navigation":
            original_get(cast(NavigationHandler, request))
            return
        try:
            respond(request, 200, [link.model_dump() for link in store.current()])
        except sqlite3.Error:
            respond(request, 503, {"detail": "Navigation storage unavailable"})

    def post(request: BaseHTTPRequestHandler) -> None:
        if request.path != "/api/vr-navigation":
            original_post(cast(NavigationHandler, request))
            return
        if request.headers.get("Origin") not in (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        ):
            respond(request, 403, {"detail": "Local page origin required"})
            return
        try:
            length = int(request.headers.get("Content-Length", "0"))
            if not 0 < length <= 16000:
                raise ValueError("Invalid navigation payload size")
            edit = NavigationEdit.model_validate_json(request.rfile.read(length))
            saved = store.save(edit)
            respond(
                request,
                200 if saved else 409,
                saved.model_dump()
                if saved
                else {"detail": "Navigation changed; reload before editing"},
            )
        except ValueError:
            respond(request, 400, {"detail": "Invalid navigation or source binding"})
        except sqlite3.Error:
            respond(request, 503, {"detail": "Navigation not saved; storage unavailable"})

    type.__setattr__(target, "do_GET", get)
    type.__setattr__(target, "do_POST", post)
