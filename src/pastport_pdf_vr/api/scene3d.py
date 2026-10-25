"""Additive local 3D routes using the reference review database and version checks."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from urllib.parse import urlsplit

from pastport_pdf_vr.application.reference_environment import read_json, record, string
from pastport_pdf_vr.domain.scene3d import AlignmentEdit, AnchorEdit


class Scene3DStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.attachment = record(read_json(root / "scene3d/attachment.json"))
        self.binding = string(self.attachment["binding"])
        self.database = root / "pastport_matching.sqlite3"

    def current(self) -> bytes:
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            alignment = db.execute(
                "SELECT version,payload_json FROM scene3d_alignment WHERE id=1"
            ).fetchone()
            objects = [
                dict(row)
                for row in db.execute("""SELECT o.id,o.name,o.parent_id,p.historical_id,
                p.version AS pairing_version,p.proposal_state,p.image_review,p.text_review,
                a.version,a.point_json,a.editor,a.identity_basis,a.relation_basis
                FROM modern_objects o JOIN pairings p ON p.modern_id=o.id
                JOIN scene3d_anchors a ON a.object_id=o.id
                AND a.historical_id IS p.historical_id""")
            ]
        payload = {
            **self.attachment,
            "alignment": {**json.loads(alignment[1]), "version": alignment[0]},
            "objects": objects,
        }
        return json.dumps(payload, ensure_ascii=False).encode()

    def save_alignment(self, edit: AlignmentEdit) -> bool:
        if edit.scene_binding != self.binding:
            raise ValueError("Scene binding changed")
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            # Existing confirmed anchors cannot silently follow a changed alignment.
            if db.execute(
                "SELECT 1 FROM scene3d_anchors WHERE point_json IS NOT NULL LIMIT 1"
            ).fetchone():
                raise ValueError("Remove confirmed 3D anchors before changing camera alignment")
            changed = db.execute(
                "UPDATE scene3d_alignment SET version=version+1,payload_json=? "
                "WHERE id=1 AND version=?",
                (edit.model_dump_json(), edit.expected_version),
            ).rowcount
            if changed:
                db.execute(
                    "INSERT INTO scene3d_events VALUES (?,?,?,?,?,?)",
                    (
                        f"alignment-{edit.expected_version + 1}",
                        hashlib.sha256(edit.model_dump_json().encode()).hexdigest(),
                        0,
                        edit.expected_version,
                        edit.model_dump_json(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
            return bool(changed)

    def save_anchor(self, edit: AnchorEdit) -> bool:
        if edit.scene_binding != self.binding:
            raise ValueError("Scene binding changed")
        request_hash = hashlib.sha256(edit.model_dump_json().encode()).hexdigest()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT request_sha256 FROM scene3d_events WHERE operation_id=?",
                (edit.operation_id,),
            ).fetchone()
            if previous:
                if previous[0] != request_hash:
                    raise ValueError("Operation reused with different content")
                return True
            alignment = json.loads(
                db.execute("SELECT payload_json FROM scene3d_alignment WHERE id=1").fetchone()[0]
            )
            if edit.point is not None and not alignment["confirmed"]:
                raise ValueError("Confirm panorama camera alignment first")
            identity = db.execute(
                """SELECT o.parent_id FROM modern_objects o JOIN pairings p ON p.modern_id=o.id
                WHERE o.id=? AND p.historical_id=? AND p.image_review!='unsuitable'
                AND p.text_review!='unsuitable' AND 
                p.proposal_state!='invalid_structural_relation' """,
                (edit.object_id, edit.historical_id),
            ).fetchone()
            if identity is None:
                raise ValueError("Object binding is rejected, missing or changed")
            if edit.point is not None and identity[0] is not None:
                whole = db.execute(
                    "SELECT point_json FROM scene3d_anchors WHERE object_id=?", (identity[0],)
                ).fetchone()
                if not edit.relation_basis.strip() or whole is None or whole[0] is None:
                    raise ValueError("Confirm the whole first and record physical part membership")
            if (
                edit.point is None
                and db.execute(
                    """SELECT 1 FROM modern_objects o JOIN scene3d_anchors a ON a.object_id=o.id
                WHERE o.parent_id=? AND a.point_json IS NOT NULL LIMIT 1""",
                    (edit.object_id,),
                ).fetchone()
            ):
                raise ValueError("Remove the whole's confirmed parts first")
            changed = db.execute(
                """UPDATE scene3d_anchors SET point_json=?,version=version+1,
                editor=?,identity_basis=?,relation_basis=? WHERE object_id=? AND 
                historical_id=? AND version=?""",
                (
                    edit.point.model_dump_json() if edit.point else None,
                    edit.editor,
                    edit.identity_basis,
                    edit.relation_basis,
                    edit.object_id,
                    edit.historical_id,
                    edit.expected_version,
                ),
            ).rowcount
            if changed:
                db.execute(
                    "INSERT INTO scene3d_events VALUES (?,?,?,?,?,?)",
                    (
                        edit.operation_id,
                        request_hash,
                        edit.object_id,
                        edit.expected_version,
                        edit.model_dump_json(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
            return bool(changed)


def install_routes(handler: type[BaseHTTPRequestHandler], root: Path, port: int) -> None:
    """Wrap trusted handler methods only when a 3D attachment exists."""
    store = Scene3DStore(root)
    get_method, post_method = "do_GET", "do_POST"
    original_get = cast(Callable[[BaseHTTPRequestHandler], None], getattr(handler, get_method))
    original_post = cast(Callable[[BaseHTTPRequestHandler], None], getattr(handler, post_method))

    def respond(request: BaseHTTPRequestHandler, code: int, body: bytes) -> None:
        request.send_response(code)
        request.send_header("Content-Type", "application/json; charset=utf-8")
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        request.end_headers()
        request.wfile.write(body)

    def get(request: BaseHTTPRequestHandler) -> None:
        route = urlsplit(request.path).path
        if route == "/api/scene3d-export":
            from pastport_pdf_vr.application.scene3d_export import export_scene

            try:
                with TemporaryDirectory(prefix="pastport-export-") as temporary:
                    archive = Path(temporary) / "pastport-scene3d.zip"
                    export_scene(root, archive)
                    with archive.open("rb") as stream:
                        request.send_response(200)
                        request.send_header("Content-Type", "application/zip")
                        request.send_header(
                            "Content-Disposition", 'attachment; filename="pastport-scene3d.zip"'
                        )
                        request.send_header("Content-Length", str(archive.stat().st_size))
                        request.end_headers()
                        shutil.copyfileobj(stream, request.wfile, 65536)
            except (OSError, ValueError, sqlite3.Error):
                request.close_connection = True
            return
        if route == "/api/scene3d":
            try:
                respond(request, 200, store.current())
            except (OSError, ValueError, sqlite3.Error):
                request.send_error(503, "3D data unavailable")
            return
        if route.startswith("/scene3d/"):
            name = route.removeprefix("/scene3d/")
            allowed = {
                "index.html",
                "viewer.js",
                "scene.json",
                "attachment.json",
                "scene.spz",
                "collider.glb",
                "panorama.jpg",
                "source-panorama.jpg",
                "source-panorama.png",
                "spark.module.js",
                "three.module.js",
                "three.core.js",
                "GLTFLoader.js",
                "BufferGeometryUtils.js",
            }
            if name not in allowed:
                request.send_error(404)
                return
            path = root / "scene3d" / name
            try:
                with path.open("rb") as stream:
                    request.send_response(200)
                    request.send_header(
                        "Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream"
                    )
                    request.send_header("Content-Length", str(path.stat().st_size))
                    request.send_header("X-Content-Type-Options", "nosniff")
                    request.end_headers()
                    shutil.copyfileobj(stream, request.wfile, 65536)
            except OSError:
                request.close_connection = True
            return
        original_get(request)

    def post(request: BaseHTTPRequestHandler) -> None:
        if request.path not in ("/api/scene3d/anchor", "/api/scene3d/alignment"):
            original_post(request)
            return
        if request.headers.get("Origin") not in (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        ):
            request.send_error(403)
            return
        try:
            length = int(request.headers.get("Content-Length", "0"))
            if not 0 < length <= 16000:
                raise ValueError("Invalid payload size")
            raw = request.rfile.read(length)
            saved = (
                store.save_anchor(AnchorEdit.model_validate_json(raw))
                if request.path.endswith("/anchor")
                else store.save_alignment(AlignmentEdit.model_validate_json(raw))
            )
            respond(request, 200 if saved else 409, json.dumps({"saved": saved}).encode())
        except ValueError as error:
            respond(request, 422, json.dumps({"detail": str(error)}).encode())
        except sqlite3.Error:
            request.send_error(503, "3D save unavailable; no success reported")

    setattr(handler, get_method, get)
    setattr(handler, post_method, post)
