"""Headless candidate initialization preserves edits and rejects stale calibration."""

import hashlib
import json
from pathlib import Path

import pytest
import pastport_matched_environment.application.scene3d_projection as projection
from pastport_matched_environment.domain.scene3d import Point3D
import struct


def collider() -> bytes:
    # Asset Y is inverted by the same fixed quaternion as the SDK viewer.
    vertices = [
        (-20, 0, -20),
        (20, 0, -20),
        (20, 0, 20),
        (-20, 0, -20),
        (20, 0, 20),
        (-20, 0, 20),
        (2, 0, -20),
        (2, -3, -20),
        (2, -3, 20),
        (2, 0, -20),
        (2, -3, 20),
        (2, 0, 20),
    ]
    binary = b"".join(struct.pack("<fff", *v) for v in vertices)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(binary)}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(vertices),
                "type": "VEC3",
                "min": [-20, -3, -20],
                "max": [20, 0, 20],
            }
        ],
    }
    raw = json.dumps(document).encode()
    raw += b" " * (-len(raw) % 4)
    return (
        struct.pack("<III", 0x46546C67, 2, 28 + len(raw) + len(binary))
        + struct.pack("<II", len(raw), 0x4E4F534A)
        + raw
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def state(root: Path):
    directory = root / "scene3d"
    directory.mkdir()
    raw = collider()
    (directory / "collider.glb").write_bytes(raw)
    return projection._State.model_validate_json(
        json.dumps(
            {
                "binding": "scene-binding",
                "scene": {
                    "collider": "collider.glb",
                    "collider_sha256": hashlib.sha256(raw).hexdigest(),
                    "metric_scale_factor": 1.0,
                    "ground_plane_offset": 0.0,
                },
                "alignment": {
                    "origin": {"x": 0.0, "y": 1.6, "z": 0.0},
                    "yaw_degrees": 0.0,
                    "pitch_degrees": 0.0,
                    "roll_degrees": 0.0,
                    "confirmed": True,
                    "version": 2,
                    "editor": "owner",
                },
                "objects": [
                    {
                        "id": n,
                        "historical_id": "h" + str(n),
                        "image_review": "pending",
                        "text_review": "pending",
                        "proposal_state": "candidate",
                        "point_json": None,
                    }
                    for n in (1, 2)
                ],
                "source_hotspots": [{"object_id": n, "yaw": 90.0, "pitch": 0.0} for n in (1, 2)],
                "candidates": [{"object_id": 1, "point_json": '{"x":9.0,"y":1.0,"z":9.0}'}],
            }
        )
    )


def test_headless_geometry_and_preserved_coordinate(tmp_path):
    current = state(tmp_path)
    probe = projection._Probe(
        origin=Point3D(x=0.0, y=1.6, z=0.0),
        scale=1.0,
        ground=0.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        nodes=(
            projection._Ray(
                object_id=1, yaw=90.0, pitch=0.0, preserve=True, point=Point3D(x=9.0, y=1.0, z=9.0)
            ),
            projection._Ray(object_id=2, yaw=90.0, pitch=0.0, preserve=False, point=None),
        ),
    )
    result = projection.OfflineCandidateProjector()._cast(tmp_path, current, probe)
    assert result.positions[0].point == probe.nodes[0].point
    assert result.positions[1].point is not None
    assert result.positions[1].point.x == pytest.approx(2.0)
    (tmp_path / "scene3d/collider.glb").write_bytes(b"changed")
    with pytest.raises(projection.CandidateProjectionError, match="changed"):
        projection.OfflineCandidateProjector()._cast(tmp_path, current, probe)


def test_existing_candidates_preserved_and_calibration_conflict_rejected(tmp_path, monkeypatch):
    current = state(tmp_path)
    batches = []

    class Store:
        def __init__(self, root):
            pass

        def initialize_candidates(self):
            pass

        def current(self):
            return current.model_dump_json()

        def save_candidates(self, batch):
            batches.append(batch)
            return False

    monkeypatch.setattr(projection, "Scene3DStore", Store)
    with pytest.raises(projection.CandidateProjectionError, match="Calibration changed"):
        projection.OfflineCandidateProjector().initialize(tmp_path)
    assert batches[0].positions[0].point == Point3D(x=9.0, y=1.0, z=9.0)
    assert not (tmp_path / "scene3d/offline-candidate-projection.json").exists()
