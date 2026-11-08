"""Read explicitly registered SDK worlds into Story's typed spatial input."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from pastport.adapters.resources import LocalResourceReader
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer, Identifier, Sha256
from pastport.domain.story_inputs import (
    EnvironmentSnapshot,
    MetricSpatialContent,
    MetricSpatialSnapshot,
    SpatialCalibration,
    SpatialGeometryAssessment,
    SpatialGeometryResult,
    SpatialNavigationLink,
    SpatialObjectLocation,
    SpatialPoint,
    SpatialTaskRules,
    SpatialWorld,
)
from pastport.ports.modules import ExecutionContext


class _Native(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _Binding(_Native):
    source_root: str


class _Scene(_Native):
    scene_id: Identifier
    binding: Sha256
    collider: str
    collider_sha256: Sha256
    coordinate_frame: Literal["three_metric_y_up"]
    metric_scale_factor: float = Field(gt=0, allow_inf_nan=False)
    ground_plane_offset: float = Field(allow_inf_nan=False)


class _Anchor(_Native):
    id: int = Field(ge=1)
    point_json: str | None
    version: int = Field(ge=0)


class _Candidate(_Native):
    object_id: int = Field(ge=1)
    point_json: str | None


class _Occurrence(_Native):
    object_id: int = Field(ge=1)


class _Calibration(_Native):
    origin: SpatialPoint
    yaw_degrees: float
    pitch_degrees: float
    roll_degrees: float
    version: int
    confirmed: bool


class _Payload(_Native):
    scene: _Scene
    binding: Sha256
    source_scene_id: Identifier
    source_import_sha256: Sha256
    alignment: _Calibration
    objects: Annotated[tuple[_Anchor, ...], Field(max_length=1000)]
    candidates: Annotated[tuple[_Candidate, ...], Field(max_length=1000)]
    source_hotspots: Annotated[tuple[_Occurrence, ...], Field(max_length=1000)]


class _Arrow(_Native):
    hotspot_id: Identifier
    target_scene_id: Identifier
    target_url: str = Field(max_length=2000)
    point: SpatialPoint | None = None
    version: int = Field(default=0, ge=0)


@dataclass(frozen=True, slots=True)
class RegisteredSpatialWorld:
    directory: Path
    attachment_sha256: str
    collider_sha256: str

    def __post_init__(self) -> None:
        class Identity(_Native):
            attachment_sha256: Sha256
            collider_sha256: Sha256

        Identity(
            attachment_sha256=self.attachment_sha256,
            collider_sha256=self.collider_sha256,
        )


class SdkEnvironmentSpatialReader:
    """SDK remains the owner of native geometry and persisted coordinate semantics."""

    def __init__(
        self,
        worlds: tuple[RegisteredSpatialWorld, ...],
        content_authority_root: Path,
        rules: SpatialTaskRules | None = None,
        *,
        analyze_geometry: bool = True,
        geometry_cache: Path | None = None,
    ) -> None:
        if not 1 <= len(worlds) <= 100:
            raise ValueError("Register 1 to 100 spatial worlds")
        self.worlds = worlds
        self.authority = content_authority_root.resolve(strict=True)
        self.rules = rules or SpatialTaskRules()
        self.analyze_geometry = analyze_geometry
        self.geometry_cache = geometry_cache

    def read_spatial(
        self, snapshot: EnvironmentSnapshot, context: ExecutionContext
    ) -> MetricSpatialSnapshot:
        try:
            from pastport_matched_environment.api.scene3d import Scene3DStore
        except ImportError as error:
            raise ServiceError(
                "ENVIRONMENT_SPATIAL_UNAVAILABLE", "Install the configured authoring SDK", 503
            ) from error
        worlds: list[SpatialWorld] = []
        try:
            for registration in self.worlds:
                context.cancellation.raise_if_cancelled()
                if datetime.now(UTC) >= context.metadata.deadline:
                    raise ServiceError("EXECUTION_DEADLINE_EXCEEDED", "Spatial read expired", 408)
                root = registration.directory
                if root.is_symlink() or not root.is_dir():
                    raise ValueError("Register a regular spatial result directory")
                files = LocalResourceReader(root)
                attachment = files.file("scene3d/attachment.json", 2 * 1024 * 1024)
                if hashlib.sha256(attachment).hexdigest() != registration.attachment_sha256:
                    raise ServiceError("ENVIRONMENT_INPUT_CHANGED", "3D attachment changed")
                if (
                    hashlib.sha256(files.file("import-manifest.json", 2 * 1024**2)).hexdigest()
                    != snapshot.import_manifest_sha256
                ):
                    raise ServiceError("ENVIRONMENT_INPUT_CHANGED", "3D belongs to another import")
                binding = _Binding.model_validate_json(files.file("shared-content.json", 65536))
                authority = Path(binding.source_root)
                if authority.is_symlink() or authority.resolve(strict=True) != self.authority:
                    raise ServiceError(
                        "ENVIRONMENT_AUTHORITY_DENIED", "Unregistered 3D authority", 403
                    )
                for path in (
                    root / "pastport_matching.sqlite3",
                    self.authority / "pastport_matching.sqlite3",
                ):
                    if (
                        path.is_symlink()
                        or not path.is_file()
                        or path.stat().st_size > 64 * 1024**2
                    ):
                        raise ValueError("Spatial database is missing or outside its read profile")
                payload = _Payload.model_validate_json(Scene3DStore(root).current())
                if payload.source_import_sha256 != snapshot.import_manifest_sha256:
                    raise ServiceError("ENVIRONMENT_INPUT_CHANGED", "3D source identity changed")
                collider = files.file("scene3d/" + payload.scene.collider, 100 * 1024**2)
                if (
                    hashlib.sha256(collider).hexdigest() != registration.collider_sha256
                    or payload.scene.collider_sha256 != registration.collider_sha256
                ):
                    raise ServiceError("ENVIRONMENT_INPUT_CHANGED", "Registered collider changed")
                candidates = {item.object_id: item.point_json for item in payload.candidates}
                occurrences = {item.object_id for item in payload.source_hotspots}
                registered = {item.object_number for item in snapshot.objects}
                # A reviewed surface placement can establish a 3D occurrence without a VR hotspot.
                occurrences.update(item.id for item in payload.objects
                                   if item.id in registered and item.point_json and item.version > 0)
                objects = []
                for item in payload.objects:
                    if item.id not in occurrences:
                        continue
                    point = item.point_json or candidates.get(item.id)
                    basis: Literal["saved_anchor", "automatic_candidate", "missing"] = (
                        "saved_anchor"
                        if item.point_json
                        else "automatic_candidate"
                        if point
                        else "missing"
                    )
                    objects.append(
                        SpatialObjectLocation(
                            object_number=item.id,
                            point=SpatialPoint.model_validate_json(point) if point else None,
                            basis=basis,
                            version=item.version,
                        )
                    )
                world = SpatialWorld(
                    view_id=payload.source_scene_id,
                    world_id=payload.scene.scene_id,
                    scene_binding=payload.binding,
                    interaction_content_revision=snapshot.content_revision,
                    world_binding=payload.scene.binding,
                    collider_sha256=payload.scene.collider_sha256,
                    coordinate_frame=payload.scene.coordinate_frame,
                    metric_scale_factor=payload.scene.metric_scale_factor,
                    ground_plane_offset=payload.scene.ground_plane_offset,
                    calibration=SpatialCalibration.model_validate(payload.alignment.model_dump()),
                    objects=tuple(objects),
                    navigation=self._arrows(root, payload.binding),
                )
                if self.analyze_geometry:
                    world = self._assess(world, collider, snapshot, context, self.geometry_cache)
                worlds.append(world)
        except (ValueError, OSError, sqlite3.Error) as error:
            raise ServiceError(
                "ENVIRONMENT_SPATIAL_INVALID", "Registered 3D state could not be validated", 503
            ) from error
        rules = self.rules
        if self.analyze_geometry:
            from pastport_matched_environment.application.spatial_analysis import (
                OfflineSpatialAnalyzer,
            )

            values = {
                "maximum_step_height": 0.35,
                "ground_sample_spacing": 0.2,
                "maximum_approach_distance": 20.0,
                "approach_standoff": 1.4,
                "rule_source_sha256": hashlib.sha256(
                    OfflineSpatialAnalyzer().policy_source
                ).hexdigest(),
            }
            if any(getattr(rules, key) not in (None, value) for key, value in values.items()):
                raise ServiceError(
                    "ENVIRONMENT_RULE_MISMATCH", "Configured movement policy differs"
                )
            rules = SpatialTaskRules.model_validate(rules.model_dump() | values)
        content = MetricSpatialContent(worlds=tuple(worlds), rules=rules)
        return MetricSpatialSnapshot(
            worlds=content.worlds,
            rules=content.rules,
            revision=CanonicalSerializer.digest(content),
            assessment=(
                "geometry_computed"
                if all(w.geometry and w.geometry.status == "computed" for w in worlds)
                else "partial"
                if any(w.geometry is not None for w in worlds)
                else "not_evaluated"
            ),
        )

    @staticmethod
    def _assess(
        world: SpatialWorld,
        collider: bytes,
        snapshot: EnvironmentSnapshot,
        context: ExecutionContext,
        geometry_cache: Path | None = None,
    ) -> SpatialWorld:
        from pastport_matched_environment.application.spatial_analysis import (
            OfflineSpatialAnalyzer,
            SpatialAnalysisError,
        )
        from pastport_matched_environment.domain.spatial_analysis import SpatialProbeRequest

        analyzer = OfflineSpatialAnalyzer(cache_directory=geometry_cache)
        catalogue = {item.object_number: item for item in snapshot.objects}

        def interactions(number: int) -> tuple[str, ...]:
            item = catalogue[number]
            parent = next((o for o in world.objects if o.object_number == item.parent_number), None)
            has_point = (
                next(o for o in world.objects if o.object_number == number).point is not None
            )

            def eligible(candidate: int) -> bool:
                value = catalogue.get(candidate)
                return bool(
                    value
                    and value.historical_id
                    and value.image_review != "unsuitable"
                    and value.text_review != "unsuitable"
                    and value.proposal_state != "invalid_structural_relation"
                )

            # Match the existing SDK viewer's marker and parent eligibility rules.
            if (
                has_point
                and item.historical_id
                and item.image_review != "unsuitable"
                and item.text_review != "unsuitable"
                and item.proposal_state != "invalid_structural_relation"
                and (
                    item.parent_number is None
                    or (
                        parent and parent.basis == "saved_anchor" and eligible(parent.object_number)
                    )
                )
            ):
                return ("inspect",)
            return ()

        request = SpatialProbeRequest.model_validate_json(
            json.dumps(
                {
                    "origin": world.calibration.origin.model_dump(),
                    "metric_scale_factor": world.metric_scale_factor,
                    "ground_plane_offset": world.ground_plane_offset,
                    "nodes": [
                        {
                            "key": f"object:{o.object_number}",
                            "point": o.point.model_dump() if o.point else None,
                            "interactions": interactions(o.object_number),
                        }
                        for o in world.objects
                    ]
                    + [
                        {
                            "key": f"arrow:{link.hotspot_id}",
                            "point": link.point.model_dump() if link.point else None,
                            "interactions": ("navigate",) if link.point is not None else (),
                        }
                        for link in world.navigation
                    ],
                }
            )
        )

        def check_active() -> None:
            context.cancellation.raise_if_cancelled()
            if datetime.now(UTC) >= context.metadata.deadline:
                raise ServiceError("EXECUTION_DEADLINE_EXCEEDED", "Spatial read expired", 408)

        result = None
        limitation = (
            "Direct geometry routes and anchor sight rays only; candidate positions and "
            "unconfirmed calibration remain unverified. Obstruction does not rule out "
            "other paths; collider rays do not establish glass transparency, object "
            "identity, detail legibility or touch reach. Cross-view travel uses registered "
            "navigation only and is not a continuous mesh path."
        )
        try:
            computed = analyzer.analyze(request, collider, check_active)
            result = SpatialGeometryResult.model_validate_json(computed.model_dump_json())
        except SpatialAnalysisError as error:
            limitation = str(error)
        assessment = SpatialGeometryAssessment(
            algorithm_sha256=hashlib.sha256(analyzer.policy_source).hexdigest(),
            input_sha256=CanonicalSerializer.digest(world),
            status="computed" if result is not None else "unknown",
            result=result,
            limitation=limitation,
        )
        return SpatialWorld.model_validate(
            world.model_dump() | {"geometry": assessment.model_dump()}
        )

    @staticmethod
    def _arrows(root: Path, binding: str) -> tuple[SpatialNavigationLink, ...]:
        database = (root / "pastport_matching.sqlite3").resolve(strict=True)
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='scene3d_arrows'"
            ).fetchone()
            rows = (
                db.execute(
                    "SELECT payload FROM scene3d_arrows WHERE binding=? "
                    "ORDER BY hotspot_id LIMIT 1001",
                    (binding,),
                ).fetchall()
                if exists
                else []
            )
        if len(rows) > 1000:
            raise ValueError("Spatial navigation exceeds profile")
        links = []
        for row in rows:
            arrow = _Arrow.model_validate_json(row[0])
            query = parse_qs(urlsplit(arrow.target_url).query)
            links.append(
                SpatialNavigationLink(
                    hotspot_id=arrow.hotspot_id,
                    target_view_id=arrow.target_scene_id,
                    point=arrow.point,
                    version=arrow.version,
                    arrival_yaw=float(query["arrival_yaw"][0]) if "arrival_yaw" in query else None,
                    arrival_pitch=float(query["arrival_pitch"][0])
                    if "arrival_pitch" in query
                    else None,
                )
            )
        return tuple(links)
