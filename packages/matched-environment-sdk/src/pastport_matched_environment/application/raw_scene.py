"""Bounded local admission of Gaussian splats and triangular collision meshes."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import signal
import subprocess
import shutil
import struct
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from pastport_matched_environment.domain.models import DomainModel


class RawSceneReceipt(DomainModel):
    schema_version: str = "pastport.raw-scene/1.0"
    splat_sha256: str
    mesh_sha256: str
    collider_sha256: str
    splat_version: int
    splat_count: int
    vertex_count: int
    triangle_count: int
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    coordinate_basis: str = "spaitial_rdf_viewer_x_rotation_180"
    metric_status: str = "provider_assumption_pending_review"
    ground_plane_offset: float = Field(allow_inf_nan=False)
    new_model_calls: int = 0
    marble_calls: int = 0


class RawSceneGeometry:
    """Preserve originals and compile a self-contained GLB without network access."""

    MAX_MESH = 100 * 1024**2
    MAX_SPLAT = 400 * 1024**2
    TYPES = {"char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1",
             "short": "i2", "ushort": "u2", "int16": "i2", "uint16": "u2",
             "int": "i4", "uint": "u4", "int32": "i4", "uint32": "u4",
             "float": "f4", "double": "f8", "float32": "f4", "float64": "f8"}

    @staticmethod
    def digest(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def admit(path: Path, maximum: int) -> None:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
            raise ValueError("Raw scene file is missing, linked, empty or outside its size limit")

    def splat_header(self, path: Path) -> tuple[int, int]:
        self.admit(path, self.MAX_SPLAT)
        try:
            with gzip.open(path, "rb") as stream:
                header = stream.read(16)
        except (OSError, EOFError) as error:
            raise ValueError("SPZ must be a readable gzip-compressed Gaussian file") from error
        if len(header) != 16:
            raise ValueError("Truncated SPZ header")
        magic, version, count, _ = struct.unpack("<4I", header)
        if magic != 0x5053474E or version not in (2, 3) or not 0 < count <= 20000000:
            raise ValueError("Unsupported SPZ signature, version or Gaussian count")
        return version, count

    def ply(self, path: Path) -> tuple[NDArray[np.float32], NDArray[np.uint32]]:
        self.admit(path, self.MAX_MESH)
        with path.open("rb") as stream:
            lines: list[str] = []
            for _ in range(100):
                raw = stream.readline(1025)
                if len(raw) > 1024:
                    raise ValueError("Oversized PLY header line")
                try:
                    line = raw.decode("ascii").strip()
                except UnicodeDecodeError as error:
                    raise ValueError("Invalid PLY header") from error
                lines.append(line)
                if line == "end_header":
                    break
            if not lines or lines[0] != "ply" or lines[-1] != "end_header":
                raise ValueError("Missing bounded PLY header")
            endian = next(("<" if "little" in line else ">" for line in lines
                           if line in ("format binary_little_endian 1.0", "format binary_big_endian 1.0")), None)
            if endian is None:
                raise ValueError("Upload a binary triangular PLY or a self-contained GLB")
            element = ""
            vertex_count = face_count = 0
            properties: list[tuple[str, str]] = []
            face_property = False
            for line in lines[2:-1]:
                tokens = line.split()
                if not tokens or tokens[0] in ("comment", "obj_info"):
                    continue
                if tokens[0] == "element":
                    if len(tokens) != 3 or tokens[1] not in ("vertex", "face"):
                        raise ValueError("Unsupported PLY element")
                    element = tokens[1]
                    if element == "vertex":
                        vertex_count = int(tokens[2])
                    else:
                        face_count = int(tokens[2])
                elif tokens[0] == "property":
                    if element == "vertex" and len(tokens) == 3 and tokens[1] in self.TYPES:
                        properties.append((tokens[2], endian + self.TYPES[tokens[1]]))
                    elif element == "face" and tokens in (
                        ["property", "list", "uchar", "int", "vertex_indices"],
                        ["property", "list", "uint8", "int32", "vertex_indices"],
                    ):
                        face_property = True
                    else:
                        raise ValueError("Unsupported PLY property")
            if not 3 <= vertex_count <= 3000000 or not 1 <= face_count <= 3000000:
                raise ValueError("PLY vertex/face count exceeds the import profile")
            if not {"x", "y", "z"} <= {name for name, _ in properties} or not face_property:
                raise ValueError("PLY needs positions and triangular face indices")
            dtype = np.dtype(properties)
            required = vertex_count * dtype.itemsize + face_count * 13
            if path.stat().st_size - stream.tell() != required:
                raise ValueError("PLY payload length differs from its triangular declaration")
            vertices = np.fromfile(stream, dtype=dtype, count=vertex_count)
            faces = np.fromfile(stream, dtype=np.dtype([("count", "u1"), ("indices", endian + "i4", (3,))]), count=face_count)
        positions = np.column_stack((vertices["x"], vertices["y"], vertices["z"])).astype(np.float32)
        if not np.isfinite(positions).all() or np.abs(positions).max() > 10000:
            raise ValueError("PLY contains nonfinite or unbounded coordinates")
        if not np.all(faces["count"] == 3) or np.any(faces["indices"] < 0) or np.any(faces["indices"] >= vertex_count):
            raise ValueError("PLY contains invalid or non-triangular faces")
        return positions, faces["indices"].astype(np.uint32)

    def capture_origin(self, mesh: Path, ground: float) -> tuple[float, float, float]:
        """Choose an observed lower-floor triangle instead of assuming a global floor height."""
        positions, indices = self.ply(mesh)
        triangles = positions[indices]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        areas = np.linalg.norm(normals, axis=1)
        centres = triangles.mean(axis=1)
        floor_mask = ((areas > 1e-8) & (np.abs(normals[:, 1]) >= 0.95 * areas)
                      & (centres[:, 1] >= ground - 0.25))
        if not np.any(floor_mask):
            # Provider origin is the conservative fallback, without inventing a floor.
            return (0.0, ground, 0.0)
        floors = centres[floor_mask]
        middle = np.average(floors, axis=0, weights=areas[floor_mask])
        distances = ((floors[:, [0, 2]] - middle[[0, 2]]) ** 2).sum(axis=1)
        floor = floors[int(np.argmin(distances))]
        return (float(floor[0]), ground - float(floor[1]) + 1.6, -float(floor[2]))

    @staticmethod
    def glb(positions: NDArray[np.float32], indices: NDArray[np.uint32], target: Path) -> None:
        position_bytes = positions.astype("<f4").tobytes()
        index_bytes = indices.astype("<u4").tobytes()
        binary = position_bytes + index_bytes
        document = {
            "asset": {"version": "2.0", "generator": "PastPort bounded PLY importer"},
            "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
                            {"buffer": 0, "byteOffset": len(position_bytes), "byteLength": len(index_bytes), "target": 34963}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
                           "min": positions.min(axis=0).tolist(), "max": positions.max(axis=0).tolist()},
                          {"bufferView": 1, "componentType": 5125, "count": int(indices.size), "type": "SCALAR"}],
        }
        encoded = json.dumps(document, separators=(",", ":")).encode()
        encoded += b" " * ((-len(encoded)) % 4)
        binary += b"\0" * ((-len(binary)) % 4)
        with target.open("xb") as stream:
            stream.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(encoded) + 8 + len(binary)))
            stream.write(struct.pack("<II", len(encoded), 0x4E4F534A))
            stream.write(encoded)
            stream.write(struct.pack("<II", len(binary), 0x004E4942))
            stream.write(binary)

    def prepare(self, splat: Path, mesh: Path, output: Path) -> RawSceneReceipt:
        version, count = self.splat_header(splat)
        self.admit(mesh, self.MAX_MESH)
        output.mkdir(parents=True, exist_ok=False)
        try:
            positions, indices = self.ply(mesh)
            self.glb(positions, indices, output / "collider.glb")
            shutil.copyfile(splat, output / "scene.spz")
            receipt = RawSceneReceipt(
                splat_sha256=self.digest(splat), mesh_sha256=self.digest(mesh),
                collider_sha256=self.digest(output / "collider.glb"),
                splat_version=version, splat_count=count, vertex_count=len(positions),
                triangle_count=len(indices), minimum=(float(positions[:, 0].min()), float(positions[:, 1].min()), float(positions[:, 2].min())),
                maximum=(float(positions[:, 0].max()), float(positions[:, 1].max()), float(positions[:, 2].max())),
                ground_plane_offset=float(np.quantile(positions[:, 1], 0.99)),
            )
            (output / "raw-scene.json").write_text(receipt.model_dump_json(indent=2))
            return receipt
        except (OSError, ValueError, OverflowError):
            shutil.rmtree(output)
            raise

class CapturedFace(DomainModel):
    file: str = Field(pattern=r"^face-[0-5]\.png$")
    matrix: tuple[float, ...] = Field(min_length=16, max_length=16)


class SceneCapture(DomainModel):
    capture_schema: str = Field(alias="schema")
    origin: tuple[float, float, float]
    faces: tuple[CapturedFace, ...] = Field(min_length=6, max_length=6)


class CapturedFaceQuality(DomainModel):
    file: str = Field(pattern=r"^face-[0-5]\.png$")
    sha256: str
    maximum_channel_std: float = Field(ge=0, allow_inf_nan=False)
    informative: bool


class CaptureQualityReport(DomainModel):
    schema_version: str = "pastport.raw-capture-quality/1"
    capture_sha256: str
    minimum_channel_std: float = 1.0
    faces: tuple[CapturedFaceQuality, ...]


class SceneCaptureRunner(Protocol):
    def capture(self, output: Path, assets: Path, log: Path) -> None: ...


class LocalSceneCapture:
    """Own the complete renderer process group, including its headless browser."""

    def capture(self, output: Path, assets: Path, log: Path) -> None:
        node = shutil.which("node")
        browser = os.environ.get("PASTPORT_CHROME") or next((str(p) for p in (
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/usr/bin/chromium"), Path("/usr/bin/google-chrome"),
        ) if p.is_file()), None)
        if node is None or browser is None:
            raise ValueError("Local SPZ capture requires Node.js and Chrome/Chromium; no model fallback")
        with log.open("ab") as stream:
            with subprocess.Popen(
                (node, str(assets / "raw_scene_render.mjs"), str(output.resolve()), str(assets), browser),
                stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, start_new_session=True,
            ) as process:
                try:
                    code = process.wait(timeout=240)
                except BaseException:
                    # Interruptions/timeouts must not leave an owned GPU browser behind.
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=3)
                    except ProcessLookupError:
                        pass
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                    raise
        if code:
            raise ValueError("Local 3D rendering failed; inspect the retained capture log")


class RawScenePreparation:
    """Create a derived observation panorama while preserving imported 3D bytes."""

    def __init__(self, capture_runner: SceneCaptureRunner | None = None) -> None:
        self.capture_runner = capture_runner or LocalSceneCapture()

    @staticmethod
    def panorama(root: Path) -> None:
        from PIL import Image

        capture = SceneCapture.model_validate_json((root / "capture.json").read_bytes())
        if len({face.file for face in capture.faces}) != 6:
            raise ValueError("Capture must contain six distinct cube faces")
        width, height = 2048, 1024
        u, v = np.meshgrid(np.arange(width), np.arange(height))
        yaw = ((u + 0.5) / width - 0.5) * (2 * np.pi)
        pitch = (0.5 - (v + 0.5) / height) * np.pi
        directions = np.stack((np.sin(yaw)*np.cos(pitch), np.sin(pitch), -np.cos(yaw)*np.cos(pitch)), axis=-1).reshape(-1, 3)
        chosen = np.full(width*height, -np.inf)
        pixels = np.zeros((width*height, 3), dtype=np.uint8)
        qualities: list[CapturedFaceQuality] = []
        for face in capture.faces:
            rotation = np.asarray(face.matrix).reshape(4, 4, order="F")[:3, :3]
            local = directions @ rotation
            depth = -local[:, 2]
            mask = (depth > chosen) & (depth > 0)
            with Image.open(root / face.file) as image:
                frame = np.asarray(image.convert("RGB"))
            contrast = float(frame.std(axis=(0, 1)).max())
            qualities.append(CapturedFaceQuality(
                file=face.file, sha256=RawSceneGeometry.digest(root / face.file),
                maximum_channel_std=contrast, informative=contrast >= 1.0,
            ))
            # Empty directions remain empty; never stretch neighbouring content into them.
            x = np.clip(((local[mask, 0]/depth[mask]+1)*0.5*frame.shape[1]).astype(int), 0, frame.shape[1]-1)
            y = np.clip(((1-local[mask, 1]/depth[mask])*0.5*frame.shape[0]).astype(int), 0, frame.shape[0]-1)
            pixels[mask] = frame[y, x]
            chosen[mask] = depth[mask]
        report = CaptureQualityReport(
            capture_sha256=RawSceneGeometry.digest(root / "capture.json"),
            faces=tuple(qualities),
        )
        (root / "capture-quality.json").write_text(report.model_dump_json(indent=2))
        if not any(face.informative for face in report.faces):
            raise ValueError("All rendered views are blank; no recognition is permitted")
        panorama_image = Image.fromarray(pixels.reshape(height, width, 3))
        panorama_image.save(root / "panorama.jpg", quality=92)

    def prepare(self, splat: Path, mesh: Path, workspace: Path) -> Path:
        import base64
        from importlib.resources import files

        output = workspace / "scene"
        importer = RawSceneGeometry()
        if output.exists():
            receipt = RawSceneReceipt.model_validate_json((output / "raw-scene.json").read_bytes())
            if receipt.splat_sha256 != importer.digest(splat) or receipt.mesh_sha256 != importer.digest(mesh):
                raise ValueError("Raw inputs changed; use a fresh workspace")
            if importer.digest(output / "scene.spz") != receipt.splat_sha256 or importer.digest(output / "collider.glb") != receipt.collider_sha256:
                raise ValueError("Registered local scene changed")
        else:
            receipt = importer.prepare(splat, mesh, output)
        assets = Path(str(files("pastport_matched_environment").joinpath("scene3d_assets")))
        if not (output / "capture.json").exists():
            template = (assets / "raw_scene_capture.html").read_text()
            origin = importer.capture_origin(mesh, receipt.ground_plane_offset)
            template = template.replace("GROUND_OFFSET", str(receipt.ground_plane_offset))
            (output / "capture.html").write_text(template.replace("CAPTURE_ORIGIN", json.dumps(origin)))
            self.capture_runner.capture(output, assets, workspace / "capture.log")
        if not (output / "panorama.jpg").exists():
            self.panorama(output)
        scene_id = "imported-" + receipt.splat_sha256[:20]
        panorama_hash = importer.digest(output / "panorama.jpg")
        from pastport_matched_environment.domain.scene3d import MarbleScene

        scene = MarbleScene(
            kind="imported_3d", scene_id=scene_id,
            binding=hashlib.sha256((receipt.model_dump_json()+panorama_hash).encode()).hexdigest(),
            splat_sha256=receipt.splat_sha256, collider_sha256=receipt.collider_sha256,
            panorama_sha256=panorama_hash, metric_scale_factor=1.0,
            ground_plane_offset=receipt.ground_plane_offset,
        )
        (output / "scene.json").write_text(scene.model_dump_json())
        uri = "data:image/jpeg;base64," + base64.b64encode((output / "panorama.jpg").read_bytes()).decode()
        tour = {"schemaVersion": 4, "id": scene_id, "firstSceneId": scene_id, "scenes": [
            {"id": scene_id, "name": "Derived view of imported 3D (not an original photograph)", "panorama": {"data": uri}, "hotspots": [], "view": {"yaw": 0, "pitch": 0, "fov": 90}}
        ]}
        html = '<script id="tour-data" type="application/json">' + json.dumps(tour).replace("</", "<\\/") + '</script>'
        (workspace / "tour.html").write_text(html)
        return workspace / "tour.html"
