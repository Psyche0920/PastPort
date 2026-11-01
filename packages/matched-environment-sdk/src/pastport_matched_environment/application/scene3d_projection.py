"""Initialize missing automatic candidates without starting a viewer or changing anchors."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from pastport_matched_environment.api.scene3d import Scene3DStore
from pastport_matched_environment.domain.scene3d import Point3D, SceneCandidate, SceneCandidateBatch


class CandidateProjectionError(ValueError):
    """Candidate projection did not complete with the registered calibration."""


class _Native(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _Object(_Native):
    id: int
    historical_id: str | None
    image_review: str
    text_review: str
    proposal_state: str
    point_json: str | None


class _Hotspot(_Native):
    object_id: int
    yaw: float
    pitch: float


class _Candidate(_Native):
    object_id: int
    point_json: str | None


class _Alignment(_Native):
    origin: Point3D
    yaw_degrees: float
    pitch_degrees: float
    roll_degrees: float
    confirmed: bool
    version: int
    editor: str = ""


class _Scene(_Native):
    collider: str
    collider_sha256: str
    metric_scale_factor: float
    ground_plane_offset: float


class _State(_Native):
    binding: str
    scene: _Scene
    alignment: _Alignment
    objects: tuple[_Object, ...]
    source_hotspots: tuple[_Hotspot, ...]
    candidates: tuple[_Candidate, ...]


class _Ray(_Native):
    object_id: int
    yaw: float
    pitch: float
    preserve: bool
    point: Point3D | None


class _Probe(_Native):
    origin: Point3D
    scale: float
    ground: float
    yaw: float
    pitch: float
    roll: float
    nodes: tuple[_Ray, ...] = Field(max_length=200)


class _Projected(_Native):
    positions: tuple[SceneCandidate, ...] = Field(max_length=200)


class OfflineCandidateProjector:
    def __init__(self, timeout_seconds: float = 60) -> None:
        if not 0 < timeout_seconds <= 120:
            raise ValueError("Projection timeout must be bounded")
        self.timeout_seconds = timeout_seconds
        self.assets = Path(__file__).resolve().parents[1] / "scene3d_assets"

    def initialize(self, root: Path) -> bool:
        store = Scene3DStore(root)
        store.initialize_candidates()
        state = _State.model_validate_json(store.current())
        targets = {
            obj.id: obj
            for obj in state.objects
            if obj.historical_id
            and obj.image_review != "unsuitable"
            and obj.text_review != "unsuitable"
            and obj.proposal_state != "invalid_structural_relation"
        }
        hotspots = tuple(item for item in state.source_hotspots if item.object_id in targets)
        candidates = {item.object_id: item.point_json for item in state.candidates}
        if all(targets[h.object_id].point_json or h.object_id in candidates for h in hotspots):
            return False
        alignment = state.alignment
        origin = alignment.origin
        if not alignment.confirmed and alignment.version == 0 and not alignment.editor:
            origin = Point3D(x=0.0, y=state.scene.ground_plane_offset, z=0.0)
        nodes = []
        for hotspot in hotspots:
            raw = targets[hotspot.object_id].point_json or candidates.get(hotspot.object_id)
            preserve = (
                bool(targets[hotspot.object_id].point_json) or hotspot.object_id in candidates
            )
            nodes.append(
                _Ray(
                    object_id=hotspot.object_id,
                    yaw=hotspot.yaw,
                    pitch=hotspot.pitch,
                    preserve=preserve,
                    point=Point3D.model_validate_json(raw) if raw else None,
                )
            )
        probe = _Probe(
            origin=origin,
            scale=state.scene.metric_scale_factor,
            ground=state.scene.ground_plane_offset,
            yaw=alignment.yaw_degrees,
            pitch=alignment.pitch_degrees,
            roll=alignment.roll_degrees,
            nodes=tuple(nodes),
        )
        projected = self._cast(root, state, probe)
        kind: Literal["human_alignment", "unconfirmed_asset_origin"] = (
            "human_alignment" if alignment.confirmed else "unconfirmed_asset_origin"
        )
        batch = SceneCandidateBatch(
            scene_binding=state.binding,
            alignment_version=alignment.version,
            origin=origin,
            alignment_kind=kind,
            positions=projected.positions,
        )
        if not store.save_candidates(batch):
            raise CandidateProjectionError("Calibration changed; candidate batch was not applied")
        (root / "scene3d/offline-candidate-projection.json").write_text(
            json.dumps(
                {
                    "algorithm_sha256": hashlib.sha256(
                        (self.assets / "project_candidates.mjs").read_bytes()
                    ).hexdigest(),
                    "collider_sha256": state.scene.collider_sha256,
                    "batch": json.loads(batch.model_dump_json()),
                    "identity_approved": False,
                },
                indent=2,
            )
        )
        return True

    def _cast(self, root: Path, state: _State, probe: _Probe) -> _Projected:
        supplied_collider = root / "scene3d" / state.scene.collider
        if supplied_collider.is_symlink() or (root / "scene3d").is_symlink():
            raise CandidateProjectionError("Collider links are not accepted")
        collider = supplied_collider.resolve()
        if not collider.is_relative_to((root / "scene3d").resolve()) or collider.is_symlink():
            raise CandidateProjectionError("Collider path escapes its registered scene")
        if not collider.is_file() or collider.stat().st_size > 100 * 1024**2:
            raise CandidateProjectionError("Collider exceeds its projection profile")
        raw_collider = collider.read_bytes()
        if hashlib.sha256(raw_collider).hexdigest() != state.scene.collider_sha256:
            raise CandidateProjectionError("Collider changed before projection")
        node = shutil.which("node")
        if node is None:
            raise CandidateProjectionError("Node.js is required for candidate projection")
        with TemporaryDirectory(prefix="pastport-candidate-projection-") as directory:
            temporary = Path(directory)
            for name in (
                "project_candidates.mjs",
                "three.module.js",
                "three.core.js",
                "GLTFLoader.js",
                "BufferGeometryUtils.js",
                "THREE-LICENSE.txt",
            ):
                content = (self.assets / name).read_text()
                if name in ("GLTFLoader.js", "BufferGeometryUtils.js"):
                    content = content.replace("from 'three'", "from './three.module.js'")
                (temporary / name).write_text(content)
            (temporary / "package.json").write_text('{"type":"module","private":true}')
            (temporary / "collider.glb").write_bytes(raw_collider)
            try:
                result = subprocess.run(
                    [node, "--max-old-space-size=512", "project_candidates.mjs"],
                    cwd=temporary,
                    input=probe.model_dump_json(),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    env={"PATH": os.environ.get("PATH", os.defpath)},
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise CandidateProjectionError(
                    "Offline candidate projection did not finish"
                ) from error
        if result.returncode or len(result.stdout) > 1024**2:
            raise CandidateProjectionError("Offline candidate projection failed")
        return _Projected.model_validate_json(result.stdout)

    def initialize_arrows(self, root: Path) -> int:
        from pastport_matched_environment.application.scene3d_arrows import Scene3DArrowStore
        from pastport_matched_environment.domain.scene3d import Scene3DArrowEdit

        arrows = Scene3DArrowStore(root)
        missing = tuple(arrow for arrow in arrows.current().arrows if arrow.point is None)
        if not missing:
            return 0
        state = _State.model_validate_json(Scene3DStore(root).current())
        alignment = state.alignment
        origin = alignment.origin
        if not alignment.confirmed and alignment.version == 0 and not alignment.editor:
            origin = Point3D(x=0.0, y=state.scene.ground_plane_offset, z=0.0)
        probe = _Probe(
            origin=origin,
            scale=state.scene.metric_scale_factor,
            ground=state.scene.ground_plane_offset,
            yaw=alignment.yaw_degrees,
            pitch=alignment.pitch_degrees,
            roll=alignment.roll_degrees,
            nodes=tuple(
                _Ray(object_id=index, yaw=arrow.yaw, pitch=arrow.pitch, preserve=False, point=None)
                for index, arrow in enumerate(missing, 1)
            ),
        )
        positions = self._cast(root, state, probe).positions
        saved = 0
        for position in positions:
            if not 1 <= position.object_id <= len(missing):
                raise CandidateProjectionError("Projection returned an unknown navigation index")
            arrow = missing[position.object_id - 1]
            if position.point is not None:
                result = arrows.save(
                    Scene3DArrowEdit(
                        scene_binding=state.binding,
                        hotspot_id=arrow.hotspot_id,
                        expected_version=arrow.version,
                        operation_id=str(uuid4()),
                        point=position.point,
                        placement="projected",
                    )
                )
                if result is None:
                    raise CandidateProjectionError(
                        "Navigation changed; projected arrow was not applied"
                    )
                saved += 1
        return saved
