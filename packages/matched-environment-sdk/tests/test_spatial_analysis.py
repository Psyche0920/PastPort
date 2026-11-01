"""Execute the packaged geometry analyzer against a deterministic floor and wall."""

import json
import struct

import pytest

from pastport_matched_environment.application.spatial_analysis import (
    OfflineSpatialAnalyzer,
    SpatialAnalysisError,
)
from pastport_matched_environment.domain.scene3d import Point3D
from pastport_matched_environment.domain.spatial_analysis import (
    SpatialProbeNode,
    SpatialProbeRequest,
)


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


def request() -> SpatialProbeRequest:
    return SpatialProbeRequest(
        origin=Point3D(x=0.0, y=1.6, z=0.0),
        metric_scale_factor=1.0,
        ground_plane_offset=0.0,
        nodes=(
            SpatialProbeNode(
                key="object:1", point=Point3D(x=0.0, y=1.0, z=5.0), interactions=("inspect",)
            ),
            SpatialProbeNode(key="object:2", point=Point3D(x=5.0, y=1.0, z=0.0)),
            SpatialProbeNode(key="object:3", point=None),
        ),
    )


def test_full_node_pass_distinguishes_direct_obstruction_from_observation() -> None:
    result = OfflineSpatialAnalyzer().analyze(request(), collider(), lambda: None)
    assert result.spawn_ground
    one, two, missing = result.objects
    assert one.route_status == "clear" and one.sight == "clear_to_anchor"
    assert two.route_status == "direct_obstructed" and two.sight == "collider_occluded"
    assert missing.route_status == "missing_position"
    assert all(item.legibility == "unknown" and item.touch == "unknown" for item in result.objects)
    assert {(edge.source, edge.target) for edge in result.routes} == {
        ("spawn", "object:1"),
        ("object:1", "spawn"),
    }
    assert all(edge.status == "clear" for edge in result.routes)
    assert one.planning.approach_station == "object:1"
    assert one.planning.enabled_interactions == ("inspect",)
    assert two.planning.approach_station is None
    assert two.planning.enabled_interactions == ()
    assert all(
        item.planning.physical_touch == "host_touch_rule_not_registered" for item in result.objects
    )
    observations = {p.station: p for p in two.planning.observation_positions}
    assert observations["spawn"].sight == "collider_occluded"
    assert observations["object:1"].sight == "collider_occluded"
    assert missing.planning.observation_positions == ()


def test_invalid_geometry_and_timeout_are_explicit_unknown_causes() -> None:
    with pytest.raises(SpatialAnalysisError, match="process failed"):
        OfflineSpatialAnalyzer().analyze(request(), b"not a glb", lambda: None)
    with pytest.raises(SpatialAnalysisError, match="timed out"):
        OfflineSpatialAnalyzer(timeout_seconds=0.00001).analyze(request(), collider(), lambda: None)


def test_cancellation_is_preserved_and_does_not_become_geometry_success() -> None:
    class Cancelled(RuntimeError):
        pass

    def check() -> None:
        raise Cancelled("cancelled")

    with pytest.raises(Cancelled):
        OfflineSpatialAnalyzer().analyze(request(), collider(), check)


def test_geometry_cache_reuses_identical_inputs_and_invalidates_changes(tmp_path, monkeypatch):
    analyzer = OfflineSpatialAnalyzer(cache_directory=tmp_path / "cache")
    original = analyzer._compute
    calls = []
    def compute(inputs, geometry, active):
        calls.append((inputs, geometry))
        return original(inputs, geometry, active)
    monkeypatch.setattr(analyzer, "_compute", compute)
    first = analyzer.analyze(request(), collider(), lambda: None)
    assert analyzer.analyze(request(), collider(), lambda: None) == first
    assert len(calls) == 1
    moved = request().model_copy(update={"origin": Point3D(x=1.0,y=1.6,z=0.0)})
    analyzer.analyze(moved, collider(), lambda: None)
    assert len(calls) == 2
    analyzer.analyze(request(), collider() + b" ", lambda: None)
    assert len(calls) == 3
    def cancelled():
        raise RuntimeError("cancelled by caller")
    with pytest.raises(RuntimeError, match="cancelled"):
        analyzer.analyze(request(), collider(), cancelled)
    assert len(calls) == 3
    for cached in (tmp_path / "cache").glob("*.json"):
        cached.write_text("broken cached JSON")
    with pytest.raises(SpatialAnalysisError, match="cache is invalid"):
        analyzer.analyze(request(), collider(), lambda: None)
