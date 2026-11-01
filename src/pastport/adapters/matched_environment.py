"""Read one registered native environment without running uploaded code or changing reviews."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import re
import sqlite3
from contextlib import closing, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pastport.adapters.resources import LocalResourceReader
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer, Contract, Identifier, Sha256
from pastport.domain.story_inputs import (
    EnvironmentContentRevision,
    EnvironmentObject,
    EnvironmentPosition,
    EnvironmentQuote,
    EnvironmentReadRequest,
    EnvironmentSnapshot,
    EnvironmentSpatialRevision,
    EnvironmentView,
)
from pastport.ports.modules import ExecutionContext
from pastport.ports.story_inputs import ContentAuthority, EnvironmentSpatialReader


class _Native(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)


class _Panorama(_Native):
    data: str


class _Hotspot(_Native):
    type: str
    targetId: str | None = None


class _Scene(_Native):
    id: Identifier
    sourceSceneId: Identifier | None = None
    panoramaRevision: Annotated[int, Field(ge=0)] = 1
    panorama: _Panorama
    hotspots: tuple[_Hotspot, ...] = ()


class _Tour(_Native):
    schemaVersion: Literal[4]
    firstSceneId: Identifier
    scenes: Annotated[tuple[_Scene, ...], Field(min_length=1, max_length=100)]


class _Manifest(_Native):
    source_pdf_sha256: Sha256


@dataclass(frozen=True, slots=True)
class EnvironmentRegistration:
    project_id: str
    environment_id: str
    directory: Path
    import_manifest_sha256: str
    source_pdf_sha256: str
    authority_roots: tuple[Path, ...] = ()
    source_profile: Literal["standard", "large_pdf"] = "standard"

    def __post_init__(self) -> None:
        class Identity(Contract):
            project_id: Identifier
            environment_id: Identifier
            import_manifest_sha256: Sha256
            source_pdf_sha256: Sha256
            source_profile: Literal["standard", "large_pdf"]

        Identity(
            project_id=self.project_id,
            environment_id=self.environment_id,
            import_manifest_sha256=self.import_manifest_sha256,
            source_pdf_sha256=self.source_pdf_sha256,
            source_profile=self.source_profile,
        )


class NativeMatchedEnvironmentReader:
    """An explicit server registration bounds all paths; local candidates remain candidates."""

    def __init__(
        self,
        registration: EnvironmentRegistration,
        *,
        content_authority: ContentAuthority | None = None,
        spatial_reader: EnvironmentSpatialReader | None = None,
    ) -> None:
        self.registration = registration
        self.content_authority = content_authority
        self.spatial_reader = spatial_reader
        self.directory = registration.directory.resolve(strict=True)
        if registration.directory.is_symlink() or not self.directory.is_dir():
            raise ValueError("Register a regular environment directory")
        self.files = LocalResourceReader(self.directory)

    async def read(
        self, request: EnvironmentReadRequest, context: ExecutionContext
    ) -> EnvironmentSnapshot:
        return await asyncio.to_thread(self._read, request, context)

    @staticmethod
    def _check(context: ExecutionContext) -> None:
        context.cancellation.raise_if_cancelled()
        if context.metadata.deadline <= datetime.now(UTC):
            raise ServiceError("EXECUTION_DEADLINE", "Environment read deadline expired")

    def _database(self) -> Path:
        binding_path = self.directory / "shared-content.json"
        authority = self.directory
        if binding_path.exists():
            # Reject a source-controlled path before the SDK follows or opens it.
            class Binding(_Native):
                source_root: str

            binding = Binding.model_validate_json(self.files.file("shared-content.json", 65536))
            candidate = Path(binding.source_root)
            allowed = {
                self.directory,
                *(p.resolve(strict=True) for p in self.registration.authority_roots),
            }
            if (
                not candidate.is_absolute()
                or candidate.is_symlink()
                or candidate.resolve() not in allowed
            ):
                raise ServiceError(
                    "ENVIRONMENT_AUTHORITY_DENIED",
                    "Shared content authority is outside registered scope",
                    403,
                )
            authority = candidate.resolve(strict=True)
            LocalResourceReader(authority).file("import-manifest.json", 2 * 1024 * 1024)
            self._safe_database(authority)
            if self.content_authority is None:
                raise ServiceError(
                    "ENVIRONMENT_AUTHORITY_UNAVAILABLE",
                    "Explicitly inject the owning SDK content authority for shared inputs",
                    503,
                )
            database = self.content_authority.database
            if database.parent.resolve() != authority:
                raise ServiceError("ENVIRONMENT_AUTHORITY_DENIED", "Shared authority changed", 403)
        database = self._safe_database(authority)
        if database.is_symlink() or not database.is_file():
            raise ServiceError(
                "ENVIRONMENT_UNAVAILABLE", "Registered review database is missing", 503
            )
        return database

    @staticmethod
    def _safe_database(root: Path) -> Path:
        database = root / "pastport_matching.sqlite3"
        for path in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
            if path.is_symlink() or (
                path.exists() and (not path.is_file() or path.stat().st_size > 64 * 1024 * 1024)
            ):
                raise ServiceError(
                    "ENVIRONMENT_INPUT_INVALID", "Review database exceeds read scope or size limits"
                )
        return database

    def _read(
        self, request: EnvironmentReadRequest, context: ExecutionContext
    ) -> EnvironmentSnapshot:
        self._check(context)
        registration = self.registration
        if (
            request.project_id != context.metadata.project_id
            or request.project_id != registration.project_id
            or request.environment_id != registration.environment_id
            or request.import_manifest_sha256 != registration.import_manifest_sha256
            or request.source_pdf_sha256 != registration.source_pdf_sha256
        ):
            raise ServiceError(
                "ENVIRONMENT_SCOPE_MISMATCH",
                "Environment is not registered for this project and source",
                403,
            )
        try:
            manifest_bytes = self.files.file("import-manifest.json", 2 * 1024 * 1024)
            if hashlib.sha256(manifest_bytes).hexdigest() != request.import_manifest_sha256:
                raise ServiceError(
                    "ENVIRONMENT_INPUT_CHANGED", "Environment import manifest changed"
                )
            manifest = _Manifest.model_validate_json(manifest_bytes)
            maximum = 512 if registration.source_profile == "large_pdf" else 64
            source = self.files.file("source.pdf", maximum * 1024 * 1024)
            if (
                manifest.source_pdf_sha256 != request.source_pdf_sha256
                or hashlib.sha256(source).hexdigest() != request.source_pdf_sha256
            ):
                raise ServiceError("ENVIRONMENT_INPUT_CHANGED", "Original source PDF changed")
            html = self.files.file("vr_trial/index.html", 64 * 1024 * 1024).decode("utf-8")
            matches = list(
                re.finditer(
                    r'<script id="tour-data" type="application/json">(.*?)</script>', html, re.S
                )
            )
            if len(matches) != 1:
                raise ValueError("Expected exactly one native tour payload")
            tour = _Tour.model_validate_json(matches[0][1])
            if tour.firstSceneId not in {s.id for s in tour.scenes}:
                raise ValueError("First scene is outside the native tour")
            views: list[EnvironmentView] = []
            current: dict[str, tuple[int, str]] = {}
            for scene in tour.scenes:
                self._check(context)
                header, encoded = scene.panorama.data.split(",", 1)
                if header not in ("data:image/jpeg;base64", "data:image/png;base64"):
                    raise ValueError("Expected a contained JPEG/PNG panorama")
                checksum = hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest()
                current[scene.id] = (scene.panoramaRevision, checksum)
                targets = tuple(
                    h.targetId
                    for h in scene.hotspots
                    if h.type == "scene" and h.targetId is not None
                )
                if any(h.type == "scene" and h.targetId is None for h in scene.hotspots):
                    raise ValueError("Navigation target is missing")
                views.append(
                    EnvironmentView(
                        view_id=scene.id,
                        source_view_id=scene.sourceSceneId or scene.id,
                        panorama_sha256=checksum,
                        panorama_revision=scene.panoramaRevision,
                        navigation_targets=targets,
                    )
                )
            self._check(context)
            authority = self._database()
            spatial = self._safe_database(self.directory)
            if spatial.is_symlink() or not spatial.is_file():
                raise ValueError("Spatial database is missing")
            with closing(
                sqlite3.connect(f"{authority.as_uri()}?mode=ro", uri=True, timeout=2)
            ) as semantic:
                spatial_connection = (
                    closing(sqlite3.connect(f"{spatial.as_uri()}?mode=ro", uri=True, timeout=2))
                    if authority != spatial
                    else nullcontext(semantic)
                )
                with spatial_connection as positions_db:
                    connections = (semantic, positions_db) if authority != spatial else (semantic,)
                    for db in connections:
                        db.row_factory = sqlite3.Row
                        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 128 * 1024)
                        db.set_progress_handler(lambda: self._progress(context), 1000)
                        db.execute("PRAGMA query_only=ON")
                        db.execute("BEGIN")
                    if authority != spatial:
                        authoritative = semantic.execute(
                            "SELECT id,stable_id FROM modern_objects ORDER BY id LIMIT 1001"
                        ).fetchall()
                        local = positions_db.execute(
                            "SELECT id,stable_id FROM modern_objects ORDER BY id LIMIT 1001"
                        ).fetchall()
                        if [tuple(row) for row in authoritative] != [tuple(row) for row in local]:
                            raise ServiceError(
                                "ENVIRONMENT_IDENTITY_CHANGED",
                                "Shared content and local spatial identities differ",
                            )
                    rows = semantic.execute("""
                        SELECT o.id,o.stable_id,o.name,o.parent_id,p.historical_id,
                        p.version AS pairing_version,p.image_review,p.text_review,p.proposal_state,
                        COALESCE(v.human_override,v.ai_draft) AS introduction,
                        COALESCE(v.version,0) AS introduction_version,psg.exact_text,psg.pdf_page,
                        t.limitation
                        FROM modern_objects o JOIN pairings p ON p.modern_id=o.id
                        LEFT JOIN vr_display_contents v ON v.object_id=o.id
                            AND v.historical_id IS p.historical_id
                        LEFT JOIN text_associations t ON t.historical_id=p.historical_id
                        LEFT JOIN passages psg ON psg.id=t.passage_id
                        ORDER BY o.id LIMIT 1001""").fetchall()
                    if len(rows) > 1000:
                        raise ValueError("Environment exceeds 1000 objects")
                    objects = tuple(
                        EnvironmentObject(
                            object_number=row["id"],
                            stable_id=row["stable_id"],
                            name=row["name"],
                            historical_id=row["historical_id"],
                            parent_number=row["parent_id"],
                            introduction=row["introduction"] or None,
                            introduction_version=row["introduction_version"],
                            pairing_version=row["pairing_version"],
                            image_review=row["image_review"],
                            text_review=row["text_review"],
                            proposal_state=row["proposal_state"],
                            evidence_limitation=row["limitation"] or None,
                            quote=EnvironmentQuote(text=row["exact_text"], pdf_page=row["pdf_page"])
                            if row["exact_text"]
                            else None,
                        )
                        for row in rows
                    )
                    stored = positions_db.execute("""SELECT object_id,scene_id,panorama_revision,
                        panorama_sha256,COALESCE(human_yaw,model_yaw) AS yaw,
                        COALESCE(human_pitch,model_pitch) AS pitch,version,human_yaw,human_pitch
                        FROM vr_positions ORDER BY object_id,scene_id LIMIT 10001""").fetchall()
                    if len(stored) > 10000:
                        raise ValueError("Environment exceeds 10000 positions")
                    positions = tuple(
                        EnvironmentPosition(
                            object_number=row["object_id"],
                            view_id=row["scene_id"],
                            yaw=float(row["yaw"]),
                            pitch=float(row["pitch"]),
                            version=row["version"],
                            placement="human_edited"
                            if row["human_yaw"] is not None and row["human_pitch"] is not None
                            else "candidate",
                        )
                        for row in stored
                        if current.get(row["scene_id"])
                        == (row["panorama_revision"], row["panorama_sha256"])
                    )
            issues: list[str] = []
            if len(stored) != len(positions):
                issues.append("Stale panorama positions were withheld.")
            if any(o.image_review != "suitable" or o.text_review != "direct" for o in objects):
                issues.append(
                    "Some matches lack explicit suitable/direct review; acceptance is not inferred."
                )
            if (self.directory / "scene3d/attachment.json").exists():
                issues.append(
                    "Only original panorama occurrences are read; "
                    "metric 3D capability is not established."
                )
            content_revision = CanonicalSerializer.digest(
                EnvironmentContentRevision(objects=objects)
            )
            spatial_revision = CanonicalSerializer.digest(
                EnvironmentSpatialRevision(
                    entry_view_id=tour.firstSceneId, views=tuple(views), positions=positions
                )
            )
            if (
                request.expected_content_revision is not None
                and request.expected_content_revision != content_revision
                or request.expected_spatial_revision is not None
                and request.expected_spatial_revision != spatial_revision
            ):
                raise ServiceError(
                    "ENVIRONMENT_REVISION_CHANGED",
                    "Requested semantic or spatial revision is stale",
                )
            self._check(context)
            snapshot = EnvironmentSnapshot(
                project_id=request.project_id,
                environment_id=request.environment_id,
                import_manifest_sha256=request.import_manifest_sha256,
                source_pdf_sha256=request.source_pdf_sha256,
                content_revision=content_revision,
                spatial_revision=spatial_revision,
                entry_view_id=tour.firstSceneId,
                views=tuple(views),
                objects=objects,
                positions=positions,
                issues=tuple(issues),
            )
            if self.spatial_reader is not None:
                metric = self.spatial_reader.read_spatial(snapshot, context)
                if (
                    request.expected_metric_revision is not None
                    and request.expected_metric_revision != metric.revision
                ):
                    raise ServiceError(
                        "ENVIRONMENT_REVISION_CHANGED", "Metric spatial revision is stale"
                    )
                snapshot = EnvironmentSnapshot.model_validate(
                    snapshot.model_dump()
                    | {
                        "metric_spatial": metric.model_dump(),
                        "spatial_profile": "metric_3d_source_bound",
                        "issues": tuple(
                            issue
                            for issue in snapshot.issues
                            if not issue.startswith("Only original panorama occurrences")
                        )
                        + ("3D positions and rules are supplied; action checks remain unknown.",),
                    }
                )
            elif request.expected_metric_revision is not None:
                raise ServiceError(
                    "ENVIRONMENT_SPATIAL_UNAVAILABLE", "No registered 3D input reader"
                )
            self._check(context)
            return snapshot

        except (
            OSError,
            UnicodeError,
            ValueError,
            ValidationError,
            sqlite3.Error,
            binascii.Error,
        ) as error:
            self._check(context)
            raise ServiceError(
                "ENVIRONMENT_INPUT_INVALID",
                "Registered environment data are invalid, unavailable or exceed read limits",
            ) from error

    @staticmethod
    def _progress(context: ExecutionContext) -> int:
        try:
            NativeMatchedEnvironmentReader._check(context)
        except (ServiceError, asyncio.CancelledError):
            return 1
        return 0
