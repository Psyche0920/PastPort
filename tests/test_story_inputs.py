"""Native input reads preserve scope, review state, manual edits and pinned revisions."""

import asyncio
import base64
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pastport.adapters.matched_environment import (
    EnvironmentRegistration,
    NativeMatchedEnvironmentReader,
)
from pastport.application.models import ServiceError
from pastport.application.updates import updated
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.story_inputs import (
    EnvironmentReadRequest,
    EnvironmentSnapshot,
    MetricSpatialContent,
    MetricSpatialSnapshot,
    SpatialCalibration,
    SpatialNavigationLink,
    SpatialObjectLocation,
    SpatialPoint,
    SpatialTaskRules,
    SpatialWorld,
)
from pastport.domain.workflow import ExecutionMetadata
from pastport.ports.modules import ExecutionContext

if TYPE_CHECKING:
    from sqlite3 import _Parameters


FIXTURES = Path(__file__).parent / "fixtures/reference"


class NotCancelled:
    def raise_if_cancelled(self) -> None:
        pass


def context() -> ExecutionContext:
    metadata = ExecutionMetadata.model_validate_json(
        (FIXTURES / "execution-metadata.json").read_bytes()
    )
    return ExecutionContext(
        updated(metadata, deadline=datetime.now(UTC) + timedelta(seconds=30)), NotCancelled()
    )


def native(root: Path) -> tuple[NativeMatchedEnvironmentReader, EnvironmentReadRequest]:
    root.mkdir()
    source = b"%PDF synthetic source, no history or real materials"
    source_hash = hashlib.sha256(source).hexdigest()
    (root / "source.pdf").write_bytes(source)
    manifest = json.dumps({"source_pdf_sha256": source_hash}).encode()
    (root / "import-manifest.json").write_bytes(manifest)
    panorama = b"synthetic panorama bytes, not visual acceptance"
    pano_hash = hashlib.sha256(panorama).hexdigest()
    (root / "vr_trial").mkdir()
    scenes = [
        {
            "id": v,
            "sourceSceneId": "original-" + v,
            "panoramaRevision": 1,
            "panorama": {"data": "data:image/jpeg;base64," + base64.b64encode(panorama).decode()},
            "hotspots": [{"type": "scene", "targetId": "two" if v == "one" else "one"}],
        }
        for v in ("one", "two")
    ]
    (root / "vr_trial/index.html").write_text(
        '<script id="tour-data" type="application/json">'
        + json.dumps({"schemaVersion": 4, "firstSceneId": "one", "scenes": scenes})
        + "</script>"
    )
    with closing(sqlite3.connect(root / "pastport_matching.sqlite3")) as db, db:
        db.executescript("""
            CREATE TABLE modern_objects(id INTEGER,stable_id TEXT,name TEXT,parent_id INTEGER);
            INSERT INTO modern_objects VALUES (27,'stable-one','Fixture whole',NULL);
            CREATE TABLE pairings(modern_id INTEGER,historical_id TEXT,version INTEGER,
                image_review TEXT,text_review TEXT,proposal_state TEXT);
            INSERT INTO pairings VALUES
                (27,'H1',0,'unreviewed','unreviewed','candidate_unreviewed');
            CREATE TABLE vr_display_contents(object_id INTEGER,historical_id TEXT,
                human_override TEXT,ai_draft TEXT,version INTEGER);
            INSERT INTO vr_display_contents VALUES(27,'H1','Human introduction','Old draft',1);
            CREATE TABLE text_associations(historical_id TEXT,passage_id INTEGER,limitation TEXT);
            INSERT INTO text_associations VALUES('H1',1,'Synthetic fixture only');
            CREATE TABLE passages(id INTEGER,exact_text TEXT,pdf_page INTEGER);
            INSERT INTO passages VALUES(1,'Synthetic located text',1);
            CREATE TABLE vr_positions(object_id INTEGER,scene_id TEXT,panorama_revision INTEGER,
                panorama_sha256 TEXT,model_yaw REAL,model_pitch REAL,human_yaw REAL,
                human_pitch REAL,version INTEGER);
        """)
        db.executemany(
            "INSERT INTO vr_positions VALUES(27,?,1,?,1.0,2.0,NULL,NULL,0)",
            ((v, pano_hash) for v in ("one", "two")),
        )
    registration = EnvironmentRegistration(
        "fixture-project",
        "environment-one",
        root,
        hashlib.sha256(manifest).hexdigest(),
        source_hash,
    )
    request = EnvironmentReadRequest(
        project_id=registration.project_id,
        environment_id=registration.environment_id,
        import_manifest_sha256=registration.import_manifest_sha256,
        source_pdf_sha256=source_hash,
        source_ref=ArtifactRef(
            artifact_id="source-1",
            project_id="fixture-project",
            kind="source",
            schema_version="0.1.0",
            content_version="1",
            sha256=source_hash,
        ),
    )
    return NativeMatchedEnvironmentReader(registration), request


def read(
    reader: NativeMatchedEnvironmentReader, request: EnvironmentReadRequest
) -> EnvironmentSnapshot:
    return asyncio.run(reader.read(request, context()))


def test_two_occurrences_share_identity_and_latest_manual_text_without_mutation(
    tmp_path: Path,
) -> None:
    reader, request = native(tmp_path / "native")
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in reader.directory.rglob("*")
        if p.is_file()
    }
    result = read(reader, request)
    assert len(result.objects) == 1 and len(result.positions) == 2
    assert result.objects[0].introduction == "Human introduction"
    assert result.objects[0].quote is not None and result.objects[0].quote.pdf_page == 1
    assert result.objects[0].image_review == "unreviewed"
    assert result.acceptance == "not_inferred"
    assert all(p.placement == "candidate" for p in result.positions)
    assert before == {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in reader.directory.rglob("*")
        if p.is_file()
    }
    assert (
        read(
            reader,
            updated(
                request,
                expected_content_revision=result.content_revision,
                expected_spatial_revision=result.spatial_revision,
            ),
        )
        == result
    )


@pytest.mark.parametrize("change", ["project", "manifest", "source"])
def test_registered_identity_and_bytes_are_required_before_reading(
    tmp_path: Path, change: str
) -> None:
    reader, request = native(tmp_path / "native")
    if change == "project":
        request = updated(request, environment_id="other")
    else:
        (
            reader.directory / ("source.pdf" if change == "source" else "import-manifest.json")
        ).write_text("changed")
    with pytest.raises(ServiceError) as error:
        read(reader, request)
    assert error.value.code in {"ENVIRONMENT_SCOPE_MISMATCH", "ENVIRONMENT_INPUT_CHANGED"}


@pytest.mark.parametrize("spatial", [False, True])
def test_changed_manual_text_or_position_invalidates_only_its_revision(
    tmp_path: Path, spatial: bool
) -> None:
    reader, request = native(tmp_path / "native")
    first = read(reader, request)
    with closing(sqlite3.connect(reader.directory / "pastport_matching.sqlite3")) as db, db:
        db.execute(
            "UPDATE vr_positions SET human_yaw=8,human_pitch=9,version=1"
            if spatial
            else "UPDATE vr_display_contents SET human_override='New human text',version=2"
        )
    second = read(reader, request)
    assert (first.content_revision == second.content_revision) == spatial
    assert (first.spatial_revision != second.spatial_revision) == spatial
    pinned = updated(
        request,
        expected_content_revision=first.content_revision,
        expected_spatial_revision=first.spatial_revision,
    )
    with pytest.raises(ServiceError) as error:
        read(reader, pinned)
    assert error.value.code == "ENVIRONMENT_REVISION_CHANGED"


def test_stale_panorama_positions_are_withheld_and_foreign_navigation_rejected(
    tmp_path: Path,
) -> None:
    reader, request = native(tmp_path / "native")
    with closing(sqlite3.connect(reader.directory / "pastport_matching.sqlite3")) as db, db:
        db.execute("UPDATE vr_positions SET panorama_sha256=?", ("f" * 64,))
    result = read(reader, request)
    assert not result.positions and any("Stale" in issue for issue in result.issues)
    path = reader.directory / "vr_trial/index.html"
    path.write_text(path.read_text().replace('"targetId": "two"', '"targetId": "outside"'))
    with pytest.raises(ServiceError) as error:
        read(reader, request)
    assert error.value.code == "ENVIRONMENT_INPUT_INVALID"


def test_authority_path_is_rejected_before_sdk_follows_it(tmp_path: Path) -> None:
    reader, request = native(tmp_path / "native")
    (reader.directory / "shared-content.json").write_text(
        json.dumps({"source_root": str(tmp_path / "outside")})
    )
    with pytest.raises(ServiceError) as error:
        read(reader, request)
    assert error.value.code == "ENVIRONMENT_AUTHORITY_DENIED"


def test_cancelled_and_expired_reads_never_open_environment(tmp_path: Path) -> None:
    reader, request = native(tmp_path / "native")

    class Cancelled:
        def raise_if_cancelled(self) -> None:
            raise ServiceError("RUN_CANCELLED", "Synthetic cancellation")

    ctx = context()
    for actual in (
        ExecutionContext(ctx.metadata, Cancelled()),
        ExecutionContext(
            updated(ctx.metadata, deadline=datetime.now(UTC) - timedelta(seconds=1)), NotCancelled()
        ),
    ):
        with pytest.raises(ServiceError) as error:
            asyncio.run(reader.read(request, actual))
        assert error.value.code in {"RUN_CANCELLED", "EXECUTION_DEADLINE"}


def test_registered_root_rejects_symlinked_databases(tmp_path: Path) -> None:
    reader, request = native(tmp_path / "native")
    database = reader.directory / "pastport_matching.sqlite3"
    backup = tmp_path / "elsewhere.sqlite3"
    shutil.move(database, backup)
    database.symlink_to(backup)
    with pytest.raises(ServiceError) as error:
        read(reader, request)
    assert error.value.code == "ENVIRONMENT_INPUT_INVALID"


def test_existing_graph_supplies_registered_environment_to_story_factory(tmp_path: Path) -> None:
    from dataclasses import replace

    from fastapi.testclient import TestClient
    from test_service import headers, settings, wait_for
    from test_shared_execution import start

    from pastport.adapters.content import (
        LocalContentFiles,
        LocalEvidenceAdapter,
        LocalNarrativeAdapter,
    )
    from pastport.api.app import create_app
    from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
    from pastport.domain.modules import (
        CandidateSetDraft,
        DiscoverRequest,
        IndexRequest,
        InventoryRequest,
        ModuleResult,
    )
    from pastport.ports.execution import ModuleServices

    reader, request = native(tmp_path / "native")
    registration = replace(reader.registration, project_id="project-1")
    reader = NativeMatchedEnvironmentReader(registration)
    request = updated(
        request,
        project_id="project-1",
        source_ref=updated(request.source_ref, project_id="project-1"),
    )
    observed: list[EnvironmentSnapshot] = []

    class Evidence(LocalEvidenceAdapter):
        def __init__(self, services: ModuleServices) -> None:
            super().__init__(LocalContentFiles(FIXTURES, allow_synthetic=True))

        async def inventory(
            self, req: InventoryRequest, ctx: ExecutionContext
        ) -> ModuleResult[SourceManifestDraft]:
            result = await super().inventory(req, ctx)
            assert result.payload is not None
            return updated(
                result,
                payload=updated(
                    result.payload,
                    sources=tuple(
                        updated(s, file_sha256=request.source_pdf_sha256)
                        for s in result.payload.sources
                    ),
                ),
            )

        async def index(
            self, req: IndexRequest, ctx: ExecutionContext
        ) -> ModuleResult[SourceIndexDraft]:
            result = await super().index(req, ctx)
            assert result.payload is not None
            return updated(
                result,
                payload=updated(
                    result.payload,
                    sources=tuple(
                        updated(s, file_sha256=request.source_pdf_sha256)
                        for s in result.payload.sources
                    ),
                ),
            )

    class Story(LocalNarrativeAdapter):
        def __init__(self, services: ModuleServices) -> None:
            super().__init__(LocalContentFiles(FIXTURES, allow_synthetic=True))
            self.services = services

        async def discover(
            self, req: DiscoverRequest, ctx: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            assert self.services.environment is not None
            source = req.index.sources[0]
            actual = updated(
                request,
                source_ref=updated(
                    request.source_ref, artifact_id=source.source_id, content_version=source.version
                ),
            )
            wrong = updated(
                actual, source_ref=updated(actual.source_ref, artifact_id="not-registered")
            )
            with pytest.raises(ServiceError) as denied:
                await self.services.environment.read(wrong, ctx)
            assert denied.value.code == "RESOURCE_NOT_REGISTERED"
            observed.append(await self.services.environment.read(actual, ctx))
            return ModuleResult[CandidateSetDraft](
                outcome="blocked",
                payload=None,
                issues=(),
                changed_ids=(),
                evidence_requests=(),
                reason="Read-only input probe completed",
            )

    with TestClient(
        create_app(
            settings(tmp_path / "main"),
            evidence_factory=Evidence,
            narrative_factory=Story,
            environment_reader=reader,
        )
    ) as client:
        run_id = start(client)
        # The existing workflow calls discover before the human direction gate.
        wait_for(client, run_id, "blocked")
        assert len(observed) == 1 and observed[0].objects[0].stable_id == "stable-one"
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert budget["used"]["model_requests"] == 0
        assert not any(budget["held"].values())


def test_allowed_shared_authority_keeps_local_positions_and_rejects_identity_drift(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    shared = pytest.importorskip("pastport_matched_environment.application.shared_content")
    reader, request = native(tmp_path / "authority")
    local = tmp_path / "derived"
    shutil.copytree(reader.directory, local)
    with closing(sqlite3.connect(reader.directory / "pastport_matching.sqlite3")) as db, db:
        db.execute("UPDATE vr_display_contents SET human_override='Canonical human edit',version=2")
        identity = shared.identity_hash(db)
    binding = shared.ContentBinding(
        source_root=str(reader.directory),
        import_sha256=request.import_manifest_sha256,
        identity_sha256=identity,
        scope=hashlib.sha256(
            (str(reader.directory) + request.import_manifest_sha256).encode()
        ).hexdigest(),
    )
    (local / "shared-content.json").write_text(binding.model_dump_json())
    with closing(sqlite3.connect(local / "pastport_matching.sqlite3")) as db, db:
        db.execute("UPDATE vr_positions SET human_yaw=12,human_pitch=4,version=1")
    registered = replace(reader.registration, directory=local, authority_roots=(reader.directory,))
    derived = NativeMatchedEnvironmentReader(
        registered, content_authority=shared.SharedContentAuthority(local)
    )
    result = read(derived, request)
    assert result.objects[0].introduction == "Canonical human edit"
    assert all(p.yaw == 12.0 and p.placement == "human_edited" for p in result.positions)
    with closing(sqlite3.connect(local / "pastport_matching.sqlite3")) as db:
        assert (
            db.execute("SELECT human_override FROM vr_display_contents").fetchone()[0]
            == "Human introduction"
        )
    with closing(sqlite3.connect(local / "pastport_matching.sqlite3")) as db, db:
        db.execute("UPDATE modern_objects SET stable_id='foreign-identity'")
    with pytest.raises(ServiceError) as error:
        read(derived, request)
    assert error.value.code == "ENVIRONMENT_IDENTITY_CHANGED"


def test_wal_reader_keeps_identity_and_positions_in_one_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, request = native(tmp_path / "native")
    database = reader.directory / "pastport_matching.sqlite3"
    original = sqlite3.connect
    with closing(original(database)) as db:
        db.execute("PRAGMA journal_mode=WAL")
    changed: list[bool] = []

    class ConcurrentEdit(sqlite3.Connection):
        def execute(self, sql: str, parameters: "_Parameters" = (), /) -> sqlite3.Cursor:
            if "FROM vr_positions ORDER BY" in sql and not changed:
                with closing(original(database)) as writer, writer:
                    writer.execute("UPDATE modern_objects SET stable_id='new-stable-id'")
                    writer.execute("UPDATE vr_positions SET human_yaw=40,human_pitch=5,version=1")
                changed.append(True)
            return super().execute(sql, parameters)

    def connect(database: str, *, uri: bool, timeout: float) -> sqlite3.Connection:
        return original(database, uri=uri, timeout=timeout, factory=ConcurrentEdit)

    monkeypatch.setattr(sqlite3, "connect", connect)
    result = read(reader, request)
    assert changed and result.objects[0].stable_id == "stable-one"
    assert all(position.yaw == 1.0 for position in result.positions)
    with closing(original(database)) as db:
        assert db.execute("SELECT stable_id FROM modern_objects").fetchone()[0] == "new-stable-id"
        assert db.execute("SELECT human_yaw FROM vr_positions LIMIT 1").fetchone()[0] == 40.0


def test_wal_committed_human_text_is_visible_and_review_rows_are_unchanged(tmp_path: Path) -> None:
    reader, request = native(tmp_path / "native")
    database = reader.directory / "pastport_matching.sqlite3"
    # Keep the writer open, so the new value exists in live WAL rather than a checkpoint.
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE vr_display_contents SET human_override='Live WAL edit',version=2")
        writer.commit()
        before = writer.execute("SELECT * FROM vr_display_contents").fetchall()
        result = read(reader, request)
        assert result.objects[0].introduction == "Live WAL edit"
        assert writer.execute("SELECT * FROM vr_display_contents").fetchall() == before


def test_large_pdf_requires_explicit_registered_profile(tmp_path: Path) -> None:
    reader, request = native(tmp_path / "large-native")
    source = reader.directory / "source.pdf"
    with source.open("wb") as stream:
        stream.write(b"%PDF bounded large-file fixture")
        stream.seek(64 * 1024 * 1024)
        stream.write(b"x")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = json.dumps({"source_pdf_sha256": source_hash}).encode()
    (reader.directory / "import-manifest.json").write_bytes(manifest)
    registration = replace(
        reader.registration,
        source_pdf_sha256=source_hash,
        import_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
    )
    request = updated(
        request,
        source_pdf_sha256=source_hash,
        import_manifest_sha256=registration.import_manifest_sha256,
        source_ref=updated(request.source_ref, sha256=source_hash),
    )
    with pytest.raises(ServiceError) as error:
        read(NativeMatchedEnvironmentReader(registration), request)
    assert error.value.code == "RESOURCE_TOO_LARGE"
    large = NativeMatchedEnvironmentReader(replace(registration, source_profile="large_pdf"))
    snapshot = read(large, request)
    assert snapshot.source_pdf_sha256 == source_hash
    assert snapshot.acceptance == "not_inferred"
    source.write_bytes(b"%PDF changed")
    with pytest.raises(ServiceError) as changed:
        read(large, request)
    assert changed.value.code == "ENVIRONMENT_INPUT_CHANGED"


def test_native_historical_identity_retains_scoped_slash(tmp_path: Path) -> None:
    reader, request = native(tmp_path / "native-id")
    with closing(sqlite3.connect(reader.directory / "pastport_matching.sqlite3")) as db, db:
        for table in ("pairings", "vr_display_contents", "text_associations"):
            db.execute(f"UPDATE {table} SET historical_id=?", ("imaret/hipped-roof",))
    result = read(reader, request)
    assert result.objects[0].historical_id == "imaret/hipped-roof"
    assert result.objects[0].introduction == "Human introduction"
    assert result.objects[0].quote is not None


class RegisteredTestSpatialReader:
    """A fixed spatial counterpart, not geometry acceptance evidence."""

    def read_spatial(
        self, snapshot: EnvironmentSnapshot, context: ExecutionContext
    ) -> MetricSpatialSnapshot:
        context.cancellation.raise_if_cancelled()
        world = SpatialWorld(
            view_id=snapshot.entry_view_id,
            world_id="world-one",
            scene_binding="a" * 64,
            world_binding="b" * 64,
            collider_sha256="c" * 64,
            coordinate_frame="three_metric_y_up",
            metric_scale_factor=1.0,
            ground_plane_offset=0.0,
            calibration=SpatialCalibration(
                origin=SpatialPoint(x=0.0, y=0.0, z=0.0),
                yaw_degrees=0.0,
                pitch_degrees=0.0,
                roll_degrees=0.0,
                version=0,
                confirmed=False,
            ),
            objects=(
                SpatialObjectLocation(
                    object_number=27,
                    point=SpatialPoint(x=1.0, y=2.0, z=3.0),
                    basis="automatic_candidate",
                    version=0,
                ),
            ),
            navigation=(
                SpatialNavigationLink(
                    hotspot_id="arrow-one",
                    target_view_id="two",
                    point=SpatialPoint(x=2.0, y=0.0, z=0.0),
                    version=2,
                    arrival_yaw=90.0,
                ),
            ),
        )
        content = MetricSpatialContent(worlds=(world,), rules=SpatialTaskRules())
        return MetricSpatialSnapshot(
            worlds=content.worlds,
            rules=content.rules,
            revision=CanonicalSerializer.digest(content),
        )


def test_metric_input_is_optional_pinned_and_does_not_promote_candidates(tmp_path: Path) -> None:
    original, request = native(tmp_path / "native")
    assert read(original, request).metric_spatial is None
    reader = NativeMatchedEnvironmentReader(
        original.registration, spatial_reader=RegisteredTestSpatialReader()
    )
    snapshot = read(reader, request)
    metric = snapshot.metric_spatial
    assert metric is not None
    assert snapshot.spatial_profile == "metric_3d_source_bound"
    assert metric.worlds[0].objects[0].approach == "unknown"
    assert metric.worlds[0].objects[0].visibility == "unknown"
    assert not metric.worlds[0].calibration.confirmed
    assert metric.worlds[0].navigation[0].version == 2
    assert snapshot.acceptance == "not_inferred"
    assert read(reader, updated(request, expected_metric_revision=metric.revision)) == snapshot
    with pytest.raises(ServiceError, match="stale"):
        read(reader, updated(request, expected_metric_revision="0" * 64))
    with pytest.raises(ServiceError, match="No registered 3D"):
        read(original, updated(request, expected_metric_revision=metric.revision))


def test_metric_contract_rejects_stale_positions_foreign_ids_and_inferred_permissions(
    tmp_path: Path,
) -> None:
    reader, request = native(tmp_path / "native")
    snapshot = read(reader, request)
    metric = RegisteredTestSpatialReader().read_spatial(snapshot, context())
    data = metric.model_dump()
    data["worlds"][0]["objects"][0]["point"]["x"] = 9.0
    with pytest.raises(ValueError, match="revision"):
        MetricSpatialSnapshot.model_validate(data)
    world = updated(metric.worlds[0], view_id="foreign")
    content = MetricSpatialContent(worlds=(world,), rules=metric.rules)
    foreign = MetricSpatialSnapshot(
        worlds=content.worlds, rules=content.rules, revision=CanonicalSerializer.digest(content)
    )
    with pytest.raises(ValueError, match="another environment"):
        updated(snapshot, spatial_profile="metric_3d_source_bound", metric_spatial=foreign)
    with pytest.raises(ValueError):
        SpatialObjectLocation.model_validate(
            {
                "object_number": 27,
                "point": None,
                "basis": "missing",
                "version": 0,
                "approach": "allowed",
            }
        )


@pytest.mark.parametrize("manual_anchor", [False, True])
def test_sdk_spatial_reader_preserves_saved_arrows_and_checks_collider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manual_anchor: bool,
) -> None:
    from pastport_matched_environment.api.scene3d import Scene3DStore

    from pastport.adapters.environment_spatial import (
        RegisteredSpatialWorld,
        SdkEnvironmentSpatialReader,
    )

    reader, request = native(tmp_path / "native")
    snapshot = read(reader, request)
    if manual_anchor:
        from pastport.domain.story_inputs import EnvironmentSpatialRevision

        revision = EnvironmentSpatialRevision(entry_view_id=snapshot.entry_view_id,
                                              views=snapshot.views, positions=())
        snapshot = updated(snapshot, positions=(), spatial_revision=CanonicalSerializer.digest(revision))
    root = reader.directory
    (root / "scene3d").mkdir()
    attachment = json.dumps({"binding": "a" * 64, "source_scene_id": "one"}).encode()
    (root / "scene3d/attachment.json").write_bytes(attachment)
    collider = b"synthetic collider: tests identity checks, not geometry"
    (root / "scene3d/collider.glb").write_bytes(collider)
    collider_hash = hashlib.sha256(collider).hexdigest()
    (root / "shared-content.json").write_text(json.dumps({"source_root": str(root)}))
    payload = json.dumps(
        {
            "scene": {
                "scene_id": "world-one",
                "binding": "b" * 64,
                "collider": "collider.glb",
                "collider_sha256": collider_hash,
                "coordinate_frame": "three_metric_y_up",
                "metric_scale_factor": 1.0,
                "ground_plane_offset": 0.0,
            },
            "binding": "a" * 64,
            "source_scene_id": "one",
            "source_import_sha256": snapshot.import_manifest_sha256,
            "alignment": {
                "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
                "yaw_degrees": 0.0,
                "pitch_degrees": 0.0,
                "roll_degrees": 0.0,
                "version": 0,
                "confirmed": False,
                "editor": "native metadata",
            },
            "objects": [{"id": 27,
                         "point_json": '{"x":1.0,"y":2.0,"z":3.0}' if manual_anchor else None,
                         "version": 1 if manual_anchor else 0}],
            "candidates": [] if manual_anchor else [{"object_id": 27, "point_json": '{"x":1.0,"y":2.0,"z":3.0}'}],
            "source_hotspots": [] if manual_anchor else [{"object_id": 27}],
        }
    )

    def current_snapshot(store: Scene3DStore) -> bytes:
        return payload.encode()

    monkeypatch.setattr(Scene3DStore, "current", current_snapshot)
    with closing(sqlite3.connect(root / "pastport_matching.sqlite3")) as db, db:
        db.execute("CREATE TABLE scene3d_arrows(binding TEXT, hotspot_id TEXT, payload TEXT)")
        db.execute(
            "INSERT INTO scene3d_arrows VALUES(?,?,?)",
            (
                "a" * 64,
                "arrow-one",
                json.dumps(
                    {
                        "hotspot_id": "arrow-one",
                        "target_scene_id": "two",
                        "yaw": 0.0,
                        "pitch": 0.0,
                        "target_url": "http://localhost/view?arrival_yaw=90&arrival_pitch=10",
                        "point": {"x": 1.0, "y": 0.0, "z": 2.0},
                        "version": 2,
                    }
                ),
            ),
        )
    spatial = SdkEnvironmentSpatialReader(
        (
            RegisteredSpatialWorld(
                root,
                hashlib.sha256(attachment).hexdigest(),
                collider_hash,
            ),
        ),
        root,
        analyze_geometry=False,
    )
    result = spatial.read_spatial(snapshot, context())
    assert result.worlds[0].navigation[0].arrival_yaw == 90.0
    assert result.worlds[0].navigation[0].version == 2
    assert result.worlds[0].objects[0].basis == ("saved_anchor" if manual_anchor else "automatic_candidate")
    assert result.worlds[0].objects[0].visibility == "unknown"
    assert not result.worlds[0].calibration.confirmed
    if manual_anchor:
        from pydantic import ValidationError
        from pastport.adapters.organizer_review import SDKOrganizerReview
        from pastport.domain.organizer_review import OrganizerReviewBinding
        from pastport_matched_environment.application.vr_positions import VRPositionService

        monkeypatch.setattr(VRPositionService, "current", lambda self: ())
        binding = OrganizerReviewBinding(root=root, worlds=(root,),
                                         import_sha256=snapshot.import_manifest_sha256)
        _, current = SDKOrganizerReview._spatial_state(binding, updated(snapshot, spatial_profile="metric_3d_source_bound", metric_spatial=result))
        assert current
        from pastport.adapters.organizer_native import NativeGameInputExporter

        prepared = updated(snapshot, spatial_profile="metric_3d_source_bound", metric_spatial=result)
        assert not prepared.positions
        assert NativeGameInputExporter.object_scene_ids(prepared, 27) == ("one",)
        assert NativeGameInputExporter.object_scene_ids(prepared, 999) == ()
        foreign_world = result.worlds[0].model_copy(update={
            "objects": (result.worlds[0].objects[0].model_copy(update={"object_number": 999}),)
        })
        foreign_content = MetricSpatialContent(worlds=(foreign_world,), rules=result.rules)
        foreign = MetricSpatialSnapshot(worlds=foreign_content.worlds, rules=foreign_content.rules,
                                        revision=CanonicalSerializer.digest(foreign_content))
        with pytest.raises(ValidationError, match="another environment"):
            updated(snapshot, spatial_profile="metric_3d_source_bound", metric_spatial=foreign)
        missing_content = MetricSpatialContent(worlds=(result.worlds[0].model_copy(update={"objects": ()}),), rules=result.rules)
        missing = MetricSpatialSnapshot(worlds=missing_content.worlds, rules=missing_content.rules, revision=CanonicalSerializer.digest(missing_content))
        _, current = SDKOrganizerReview._spatial_state(binding, updated(snapshot, spatial_profile="metric_3d_source_bound", metric_spatial=missing))
        assert not current
    (root / "scene3d/collider.glb").write_bytes(b"changed")
    with pytest.raises(ServiceError, match="collider changed"):
        spatial.read_spatial(snapshot, context())
