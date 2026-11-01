"""Bounded offline geometry subprocess using the SDK's bundled Three.js loader."""

import os
import hashlib
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from pastport_matched_environment.domain.spatial_analysis import (
    SpatialProbeRequest,
    SpatialProbeResult,
)


class SpatialAnalysisError(ValueError):
    """Geometry could not be assessed; callers must preserve an explicit unknown."""


class OfflineSpatialAnalyzer:
    def __init__(self, timeout_seconds: float = 60.0, *, cache_directory: Path | None = None) -> None:
        if not 0 < timeout_seconds <= 120:
            raise ValueError("Spatial timeout must be in (0, 120]")
        self.timeout_seconds = timeout_seconds
        self.cache_directory = cache_directory
        self.assets = Path(__file__).resolve().parents[1] / "scene3d_assets"

    @property
    def policy_source(self) -> bytes:
        return (self.assets / "spatial_analysis.mjs").read_bytes()

    def analyze(
        self,
        request: SpatialProbeRequest,
        collider: bytes,
        check_active: Callable[[], None],
    ) -> SpatialProbeResult:
        check_active()
        if self.cache_directory is None:
            return self._compute(request, collider, check_active)
        if len(collider) > 100 * 1024**2:
            raise SpatialAnalysisError("Collider exceeds the geometry profile")
        # Bind every numeric input and executable dependency. Text-only changes
        # may reuse geometry; marker, navigation, scale or algorithm edits cannot.
        identity = hashlib.sha256(request.model_dump_json().encode())
        identity.update(hashlib.sha256(collider).digest())
        for name in ("spatial_analysis.mjs", "three.module.js", "three.core.js",
                     "GLTFLoader.js", "BufferGeometryUtils.js"):
            identity.update(hashlib.sha256((self.assets / name).read_bytes()).digest())
        directory = self.cache_directory
        directory.mkdir(parents=True, exist_ok=True)
        cached = directory / (identity.hexdigest() + ".json")
        if cached.is_file():
            if cached.is_symlink() or cached.stat().st_size > 8 * 1024**2:
                raise SpatialAnalysisError("Geometry cache exceeds its trusted profile")
            try:
                result = SpatialProbeResult.model_validate_json(cached.read_bytes())
            except ValidationError as error:
                raise SpatialAnalysisError("Geometry cache is invalid") from error
            if tuple(node.key for node in request.nodes) != tuple(item.key for item in result.objects):
                raise SpatialAnalysisError("Geometry cache node identities differ")
            check_active()
            return result
        result = self._compute(request, collider, check_active)
        # Only complete validated results are reusable; readers never see a
        # partially written cache even when two local exports finish together.
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as pending:
            temporary = Path(pending.name)
            try:
                pending.write(result.model_dump_json().encode())
                pending.flush()
                check_active()
                temporary.replace(cached)
            finally:
                temporary.unlink(missing_ok=True)
        return result

    def _compute(
        self, request: SpatialProbeRequest, collider: bytes,
        check_active: Callable[[], None],
    ) -> SpatialProbeResult:
        node = shutil.which("node")
        if node is None:
            raise SpatialAnalysisError("Node.js is unavailable")
        if len(collider) > 100 * 1024**2:
            raise SpatialAnalysisError("Collider exceeds the geometry profile")
        check_active()
        with tempfile.TemporaryDirectory(prefix="pastport-spatial-") as temporary:
            root = Path(temporary)
            for name in (
                "spatial_analysis.mjs",
                "three.module.js",
                "three.core.js",
                "GLTFLoader.js",
                "BufferGeometryUtils.js",
                "THREE-LICENSE.txt",
            ):
                content = (self.assets / name).read_bytes()
                if name in {"GLTFLoader.js", "BufferGeometryUtils.js"}:
                    content = content.replace(b"from 'three'", b"from './three.module.js'")
                (root / name).write_bytes(content)
            (root / "package.json").write_text('{"type":"module","private":true}')
            (root / "collider.glb").write_bytes(collider)
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
                source.write(request.model_dump_json().encode())
                source.seek(0)
                try:
                    with subprocess.Popen(
                        [node, "--max-old-space-size=512", "spatial_analysis.mjs", "--run"],
                        cwd=root,
                        stdin=source,
                        stdout=output,
                        stderr=subprocess.DEVNULL,
                        env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                    ) as process:
                        import time

                        deadline = time.monotonic() + self.timeout_seconds
                        try:
                            while process.poll() is None:
                                check_active()
                                if time.monotonic() >= deadline:
                                    raise SpatialAnalysisError("Geometry assessment timed out")
                                try:
                                    process.wait(timeout=0.1)
                                except subprocess.TimeoutExpired:
                                    continue
                        finally:
                            if process.poll() is None:
                                process.kill()
                                process.wait()
                        if process.returncode != 0 or output.tell() > 8 * 1024**2:
                            raise SpatialAnalysisError(
                                "Geometry process failed or exceeded output limit"
                            )
                except OSError as error:
                    raise SpatialAnalysisError("Geometry process could not start") from error
                output.seek(0)
                try:
                    result = SpatialProbeResult.model_validate_json(output.read(8 * 1024**2 + 1))
                except ValidationError as error:
                    raise SpatialAnalysisError("Geometry response is invalid") from error
        check_active()
        if tuple(node.key for node in request.nodes) != tuple(item.key for item in result.objects):
            raise SpatialAnalysisError("Geometry response changed object identity")
        return result
