"""Admit existing Marble exports without generation, credentials or uploaded code."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import struct
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from pastport_pdf_vr.application.inputs import InputValidationError
from pastport_pdf_vr.application.reference_environment import (
    digest,
    read_json,
    record,
    string,
)
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.domain.scene3d import MarbleScene


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        raise InputValidationError("Marble asset redirects are not accepted")


class MarbleImporter:
    """Copy contained local assets or bounded assets from Marble's fixed CDN only."""

    def _copy(self, source: str, base: Path, target: Path, maximum: int) -> None:
        if target.exists():
            raise InputValidationError("Asset destination already exists")
        parsed = urlsplit(source)
        temporary = target.with_suffix(target.suffix + ".pending")
        try:
            if parsed.scheme:
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != "cdn.marble.worldlabs.ai"
                    or parsed.port not in (None, 443)
                    or parsed.username
                    or parsed.password
                ):
                    raise InputValidationError("Only HTTPS Marble CDN assets are accepted")
                opener = urllib.request.build_opener(NoRedirect())
                stream = opener.open(source, timeout=60)
            else:
                path = (base / source).resolve()
                if base.resolve() not in path.parents or not path.is_file():
                    raise InputValidationError("Marble assets must stay inside the export folder")
                stream = path.open("rb")
            with stream, temporary.open("xb") as output:
                total = 0
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > maximum:
                        raise InputValidationError("Marble asset exceeds the bounded import limit")
                    output.write(chunk)
            if total == 0:
                raise InputValidationError("Empty Marble asset")
            temporary.replace(target)
        except (OSError, urllib.error.URLError) as error:
            raise InputValidationError(
                "Marble asset unavailable; import stopped without generation"
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def prepare(self, source: Path, destination: Path) -> Path:
        if source.is_dir():
            candidates = list(source.rglob("world.json"))
            if len(candidates) != 1:
                raise InputValidationError("Select a folder containing exactly one world.json")
            source = candidates[0]
        if source.stat().st_size > 2 * 1024 * 1024:
            raise InputValidationError("Marble world.json exceeds 2 MiB")
        world = record(read_json(source))
        assets = record(world["assets"])
        splats = record(assets["splats"])
        urls = record(splats["spz_urls"])
        semantics = record(splats["semantics_metadata"])
        selection = urls.get("full_res") or urls.get("500k")
        identity = string(world["world_id"])
        # Source URLs can expire: source bytes remain in the upload audit, not the public result.
        destination.mkdir(parents=True, exist_ok=False)
        try:
            self._copy(string(selection), source.parent, destination / "scene.spz", 400 * 1024**2)
            self._copy(
                string(record(assets["mesh"])["collider_mesh_url"]),
                source.parent,
                destination / "collider.glb",
                100 * 1024**2,
            )
            self._copy(
                string(record(assets["imagery"])["pano_url"]),
                source.parent,
                destination / "panorama.jpg",
                30 * 1024**2,
            )
            with (destination / "collider.glb").open("rb") as collider:
                signature = collider.read(4)
            if signature != b"glTF":
                raise InputValidationError("Marble collider is not GLB")
            with (destination / "collider.glb").open("rb") as collider:
                header = collider.read(20)
                if len(header) != 20:
                    raise InputValidationError("Truncated GLB")
                magic, version, length, chunk_length, chunk_type = struct.unpack("<4sIIII", header)
                if (
                    magic != b"glTF"
                    or version != 2
                    or chunk_type != 0x4E4F534A
                    or length != (destination / "collider.glb").stat().st_size
                    or chunk_length > 4 * 1024**2
                ):
                    raise InputValidationError("Invalid or oversized GLB metadata")
                gltf = record(json.loads(collider.read(chunk_length)))
                for key in ("buffers", "images"):
                    entries = gltf.get(key, [])
                    if not isinstance(entries, list):
                        raise InputValidationError("Invalid GLB asset list")
                    if any(isinstance(entry, dict) and "uri" in entry for entry in entries):
                        raise InputValidationError(
                            "Collider must be self-contained without remote assets"
                        )
            with Image.open(destination / "panorama.jpg") as image:
                if image.width != 2 * image.height or image.width > 16384:
                    raise InputValidationError(
                        "Marble reference panorama must be a bounded 2:1 sphere"
                    )
                image.verify()
            hashes = tuple(
                digest(destination / name) for name in ("scene.spz", "collider.glb", "panorama.jpg")
            )
            metadata = json.dumps(semantics, sort_keys=True)
            binding = hashlib.sha256((identity + "".join(hashes) + metadata).encode()).hexdigest()
            scene = MarbleScene.model_validate(
                {
                    "scene_id": identity,
                    "binding": binding,
                    "splat_sha256": hashes[0],
                    "collider_sha256": hashes[1],
                    "panorama_sha256": hashes[2],
                    "metric_scale_factor": semantics["metric_scale_factor"],
                    "ground_plane_offset": semantics["ground_plane_offset"],
                }
            )
            atomic_write(destination / "scene.json", scene.model_dump_json())
            # This panorama is a PDF-inspection reference, never the 3D delivery or anchor source.
            uri = (
                "data:image/jpeg;base64,"
                + base64.b64encode((destination / "panorama.jpg").read_bytes()).decode()
            )
            data = {
                "schemaVersion": 4,
                "id": "marble-reference",
                "firstSceneId": identity,
                "scenes": [
                    {
                        "id": identity,
                        "name": "Marble reference only",
                        "panorama": {"data": uri},
                        "hotspots": [],
                    }
                ],
            }
            atomic_write(
                destination / "index.html",
                '<script id="tour-data" type="application/json">'
                + json.dumps(data).replace("</", "<\\/")
                + "</script>",
            )
            return destination / "index.html"
        except BaseException:
            shutil.rmtree(destination)
            raise


def load_scene(folder: Path) -> MarbleScene:
    scene = MarbleScene.model_validate_json((folder / "scene.json").read_bytes())
    for name, expected in (
        (scene.splat, scene.splat_sha256),
        (scene.collider, scene.collider_sha256),
        (scene.panorama, scene.panorama_sha256),
    ):
        if digest(folder / name) != expected:
            raise InputValidationError("Marble asset changed after registration")
    return scene
