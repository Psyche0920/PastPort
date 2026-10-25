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

from pastport_pdf_vr.application.reference_environment import (
    integer,
    read_json,
    record,
    sequence,
    string,
)
from pastport_pdf_vr.application.scene3d_arrows import Scene3DArrowStore
from pastport_pdf_vr.domain.scene3d import (
    AlignmentEdit,
    AnchorEdit,
    Scene3DArrowEdit,
    SceneCandidateBatch,
    SceneRenderVariant,
)


class Scene3DStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.attachment = record(read_json(root / "scene3d/attachment.json"))
        self.binding = string(self.attachment["binding"])
        self.database = root / "pastport_matching.sqlite3"

    def initialize_candidates(self) -> None:
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scene3d_candidate_batches(
                    binding TEXT NOT NULL,alignment_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,created_at TEXT NOT NULL,
                    PRIMARY KEY(binding,alignment_version));
                CREATE TABLE IF NOT EXISTS scene3d_candidates(
                    binding TEXT NOT NULL,alignment_version INTEGER NOT NULL,
                    object_id INTEGER NOT NULL,point_json TEXT,
                    PRIMARY KEY(binding,alignment_version,object_id));
            """)

    def save_candidates(self, batch: SceneCandidateBatch) -> bool:
        if batch.scene_binding != self.binding:
            raise ValueError("Candidate scene binding changed")
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            version, raw = db.execute(
                "SELECT version,payload_json FROM scene3d_alignment WHERE id=1"
            ).fetchone()
            if version != batch.alignment_version:
                return False
            alignment = json.loads(raw)
            if batch.alignment_kind == "human_alignment" and not alignment["confirmed"]:
                raise ValueError("Alignment is not human-confirmed")
            if batch.alignment_kind == "unconfirmed_asset_origin" and alignment["confirmed"]:
                return False
            allowed = {
                row[0]
                for row in db.execute(
                    "SELECT modern_id FROM pairings WHERE historical_id IS NOT NULL "
                    "AND image_review!='unsuitable' AND text_review!='unsuitable' "
                    "AND proposal_state!='invalid_structural_relation'"
                )
            }
            source = {
                integer(record(row)["object_id"])
                for row in sequence(self.attachment["source_hotspots"])
            }
            numbers = [point.object_id for point in batch.positions]
            if len(numbers) != len(set(numbers)) or set(numbers) != allowed & source:
                raise ValueError("Candidate coverage differs from current source bindings")
            db.execute(
                "INSERT OR IGNORE INTO scene3d_candidate_batches VALUES (?,?,?,?)",
                (self.binding, version, batch.model_dump_json(), datetime.now(UTC).isoformat()),
            )
            for candidate in batch.positions:
                db.execute(
                    "INSERT OR IGNORE INTO scene3d_candidates VALUES (?,?,?,?)",
                    (
                        self.binding,
                        version,
                        candidate.object_id,
                        candidate.point.model_dump_json() if candidate.point else None,
                    ),
                )
        return True

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
            candidates = [
                dict(row)
                for row in db.execute(
                    "SELECT object_id,point_json FROM scene3d_candidates "
                    "WHERE binding=? AND alignment_version=?",
                    (self.binding, alignment[0]),
                )
            ]
        payload = {
            **self.attachment,
            "alignment": {**json.loads(alignment[1]), "version": alignment[0]},
            "objects": objects,
            "candidates": candidates,
        }
        variant_path = self.root / "scene3d/render-variant.json"
        if variant_path.is_file():
            variant = SceneRenderVariant.model_validate_json(variant_path.read_bytes())
            world = record(self.attachment["scene"])
            if variant.scene_binding != self.binding or variant.world_id != world["scene_id"]:
                raise ValueError("Render variant belongs to a different scene")
            payload["render_variant"] = json.loads(variant.model_dump_json())
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
            if (
                edit.point is not None
                and not alignment["confirmed"]
                and edit.placement_method != "surface_pick"
            ):
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
    store.initialize_candidates()
    arrows = Scene3DArrowStore(root)
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
        if route == "/api/scene3d/arrows":
            try:
                respond(request, 200, arrows.current().model_dump_json().encode())
            except (ValueError, OSError, sqlite3.Error):
                request.send_error(503, "3D arrow data unavailable")
            return
        if route == "/api/scene3d/content":
            original_path = request.path
            request.path = request.path.replace("/api/scene3d/content", "/api/vr-content", 1)
            try:
                original_get(request)
            finally:
                request.path = original_path
            return
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
                "transitions.js",
                "shared_content.js",
                "portal-navigation.json",
                "scene.json",
                "attachment.json",
                "scene.spz",
                "scene-full.spz",
                "collider.glb",
                "panorama.jpg",
                "source-panorama.jpg",
                "source-panorama.png",
                "spark.module.js",
                "three.module.js",
                "three.core.js",
                "GLTFLoader.js",
                "Pass.js",
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
        if request.path == "/api/scene3d/content":
            original_path = request.path
            request.path = "/api/vr-content"
            try:
                original_post(request)
            finally:
                request.path = original_path
            return
        if request.path not in (
            "/api/scene3d/arrows/position",
            "/api/scene3d/anchor",
            "/api/scene3d/alignment",
            "/api/scene3d/candidates",
        ):
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
            limit = 128000 if request.path.endswith("/candidates") else 16000
            if not 0 < length <= limit:
                raise ValueError("Invalid payload size")
            raw = request.rfile.read(length)
            if request.path == "/api/scene3d/arrows/position":
                saved_arrow = arrows.save(Scene3DArrowEdit.model_validate_json(raw))
                respond(
                    request,
                    200 if saved_arrow else 409,
                    saved_arrow.model_dump_json().encode() if saved_arrow else b'{"saved":false}',
                )
                return
            if request.path.endswith("/candidates"):
                saved = store.save_candidates(SceneCandidateBatch.model_validate_json(raw))
            elif request.path.endswith("/anchor"):
                saved = store.save_anchor(AnchorEdit.model_validate_json(raw))
            else:
                saved = store.save_alignment(AlignmentEdit.model_validate_json(raw))
            respond(request, 200 if saved else 409, json.dumps({"saved": saved}).encode())
        except ValueError as error:
            respond(request, 422, json.dumps({"detail": str(error)}).encode())
        except sqlite3.Error:
            request.send_error(503, "3D save unavailable; no success reported")

    setattr(handler, get_method, get)
    setattr(handler, post_method, post)
