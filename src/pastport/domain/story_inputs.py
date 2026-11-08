"""Read-only, source-bound authoring input; not a new game wire or approval grant."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import (
    ArtifactRef,
    CanonicalSerializer,
    Contract,
    Identifier,
    Sha256,
    Text,
    unique,
)


class EnvironmentReadRequest(Contract):
    project_id: Identifier
    environment_id: Identifier
    import_manifest_sha256: Sha256
    source_pdf_sha256: Sha256
    source_ref: ArtifactRef
    expected_content_revision: Sha256 | None = None
    expected_spatial_revision: Sha256 | None = None
    expected_metric_revision: Sha256 | None = None

    @model_validator(mode="after")
    def source_identity(self) -> Self:
        if (
            self.source_ref.kind != "source"
            or self.source_ref.project_id != self.project_id
            or self.source_ref.sha256 != self.source_pdf_sha256
        ):
            raise ValueError("Registered source reference differs from the environment source")
        return self


class IDMLTextSelector(Contract):
    member: Text
    story_id: Identifier
    paragraph_index: Annotated[int, Field(ge=0)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("IDML text selector is inverted")
        return self


class EnvironmentQuote(Contract):
    text: Text
    pdf_page: Annotated[int, Field(ge=1)] | None = Field(default=None, exclude_if=lambda value: value is None)
    idml_selector: IDMLTextSelector | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def source_kind(self) -> Self:
        if (self.pdf_page is None) == (self.idml_selector is None):
            raise ValueError("A quote must use exactly one PDF page or native IDML selector")
        return self


HistoricalSourceId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=300,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*(/[a-zA-Z0-9][a-zA-Z0-9_.:-]*)*$",
    ),
]


class EnvironmentObject(Contract):
    object_number: Annotated[int, Field(ge=1)]
    stable_id: Identifier
    historical_id: HistoricalSourceId | None
    parent_number: Annotated[int, Field(ge=1)] | None
    name: Text
    introduction: Text | None
    introduction_version: Annotated[int, Field(ge=0)]
    pairing_version: Annotated[int, Field(ge=0)]
    image_review: Literal["unreviewed", "suitable", "unsuitable", "uncertain"]
    text_review: Literal["unreviewed", "direct", "context_only", "unsuitable", "uncertain"]
    proposal_state: Text
    evidence_limitation: Text | None
    quote: EnvironmentQuote | None


class EnvironmentView(Contract):
    view_id: Identifier
    source_view_id: Identifier
    panorama_sha256: Sha256
    panorama_revision: Annotated[int, Field(ge=0)]
    navigation_targets: tuple[Identifier, ...]


class EnvironmentPosition(Contract):
    object_number: Annotated[int, Field(ge=1)]
    view_id: Identifier
    yaw: Annotated[float, Field(ge=-180, le=180)]
    pitch: Annotated[float, Field(ge=-90, le=90)]
    version: Annotated[int, Field(ge=0)]
    placement: Literal["human_edited", "candidate"]


class EnvironmentContentRevision(Contract):
    objects: tuple[EnvironmentObject, ...]


class EnvironmentSpatialRevision(Contract):
    entry_view_id: Identifier
    views: tuple[EnvironmentView, ...]
    positions: tuple[EnvironmentPosition, ...]


class SpatialPoint(Contract):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    z: float = Field(allow_inf_nan=False)


class SpatialCalibration(Contract):
    origin: SpatialPoint
    yaw_degrees: float = Field(allow_inf_nan=False)
    pitch_degrees: float = Field(allow_inf_nan=False)
    roll_degrees: float = Field(allow_inf_nan=False)
    version: int = Field(ge=0)
    confirmed: bool


class SpatialObjectLocation(Contract):
    object_number: int = Field(ge=1)
    point: SpatialPoint | None
    basis: Literal["saved_anchor", "automatic_candidate", "missing"]
    version: int = Field(ge=0)
    visibility: Literal["unknown"] = "unknown"
    legibility: Literal["unknown"] = "unknown"
    approach: Literal["unknown"] = "unknown"
    touch: Literal["unknown"] = "unknown"

    @model_validator(mode="after")
    def point_basis(self) -> Self:
        if (self.point is None) != (self.basis == "missing"):
            raise ValueError("Spatial point and placement basis disagree")
        return self


class SpatialNavigationLink(Contract):
    hotspot_id: Identifier
    target_view_id: Identifier
    point: SpatialPoint | None
    version: int = Field(ge=0)
    arrival_yaw: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    arrival_pitch: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)


SpatialRouteStatus = Literal[
    "clear", "distance_limit", "ground_unknown", "direct_obstructed", "missing_position"
]


class SpatialObservationPosition(Contract):
    station: Identifier
    point: SpatialPoint
    distance: float = Field(ge=0, allow_inf_nan=False)
    sight: Literal["clear_to_anchor", "collider_occluded", "target_too_close"]


class SpatialPlanningFacts(Contract):
    basis: Literal["registered_geometry_not_identity_approval"]
    observation_positions: Annotated[tuple[SpatialObservationPosition, ...], Field(max_length=101)]
    approach_station: Identifier | None
    enabled_interactions: tuple[Literal["inspect", "navigate"], ...]
    detail_reading: Literal["task_specific_requirement_missing"]
    physical_touch: Literal["host_touch_rule_not_registered"]


class SpatialGeometryObject(Contract):
    key: Identifier
    route_status: SpatialRouteStatus
    route: Annotated[tuple[SpatialPoint, ...], Field(max_length=1000)]
    sight: Literal["clear_to_anchor", "collider_occluded", "target_too_close", "missing_position"]
    distance: float | None = Field(ge=0, allow_inf_nan=False)
    legibility: Literal["unknown"]
    touch: Literal["unknown"]
    planning: SpatialPlanningFacts


class SpatialGeometryRoute(Contract):
    source: Identifier
    target: Identifier
    status: SpatialRouteStatus
    points: Annotated[tuple[SpatialPoint, ...], Field(max_length=1000)]


class SpatialGeometryResult(Contract):
    policy_version: Literal["pastport.geometry-direct/1"]
    spawn_ground: bool
    spawn: SpatialPoint
    eye_height: float = Field(gt=0, allow_inf_nan=False)
    objects: Annotated[tuple[SpatialGeometryObject, ...], Field(max_length=100)]
    routes: Annotated[tuple[SpatialGeometryRoute, ...], Field(max_length=10000)]


class SpatialGeometryAssessment(Contract):
    algorithm_sha256: Sha256
    input_sha256: Sha256
    status: Literal["computed", "unknown"]
    result: SpatialGeometryResult | None
    limitation: Text

    @model_validator(mode="after")
    def assessment_state(self) -> Self:
        if (self.result is not None) != (self.status == "computed"):
            raise ValueError("Geometry assessment state and result disagree")
        return self


class SpatialWorld(Contract):
    view_id: Identifier
    world_id: Identifier
    scene_binding: Sha256
    interaction_content_revision: Sha256 | None = None
    world_binding: Sha256
    collider_sha256: Sha256
    coordinate_frame: Literal["three_metric_y_up"]
    scale_basis: Literal["generated_metadata_not_surveyed"] = "generated_metadata_not_surveyed"
    asset_orientation: tuple[Literal[1], Literal[0], Literal[0], Literal[0]] = (1, 0, 0, 0)
    metric_scale_factor: float = Field(gt=0, allow_inf_nan=False)
    ground_plane_offset: float = Field(allow_inf_nan=False)
    calibration: SpatialCalibration
    objects: tuple[SpatialObjectLocation, ...]
    navigation: tuple[SpatialNavigationLink, ...]
    geometry: SpatialGeometryAssessment | None = None

    @model_validator(mode="after")
    def geometry_identity(self) -> Self:
        if self.geometry is not None:
            if self.geometry.input_sha256 != CanonicalSerializer.digest(
                self.model_copy(update={"geometry": None})
            ):
                raise ValueError("Geometry assessment belongs to another spatial input")
            if self.geometry.result is not None:
                expected = {f"object:{o.object_number}" for o in self.objects}
                expected.update(f"arrow:{link.hotspot_id}" for link in self.navigation)
                actual = [o.key for o in self.geometry.result.objects]
                if len(actual) != len(expected) or set(actual) != expected:
                    raise ValueError("Geometry assessment changed spatial node identities")
                sources = expected | {"spawn"}
                if any(
                    r.source not in sources or r.target not in sources
                    for r in self.geometry.result.routes
                ):
                    raise ValueError("Geometry route references unknown nodes")
        return self


class SpatialTaskRules(Contract):
    version: Literal["pastport.spatial-task-rules/0.1.0"] = "pastport.spatial-task-rules/0.1.0"
    every_object_requires_approach: Literal[False] = False
    observe_requires_visibility_and_detail: Literal[True] = True
    walking_requires_continuous_ground_and_collision: Literal[True] = True
    blocked_approach_implies_observable: Literal[False] = False
    cross_view_requires_registered_arrival: Literal[True] = True
    unknown_implies_allowed: Literal[False] = False
    rule_source_sha256: Sha256 | None = None
    maximum_step_height: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    ground_sample_spacing: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    maximum_approach_distance: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    approach_standoff: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class MetricSpatialContent(Contract):
    worlds: tuple[SpatialWorld, ...]
    rules: SpatialTaskRules


class MetricSpatialSnapshot(MetricSpatialContent):
    revision: Sha256
    assessment: Literal["not_evaluated", "geometry_computed", "partial"] = "not_evaluated"

    @model_validator(mode="after")
    def exact_revision(self) -> Self:
        expected_assessment = (
            "geometry_computed"
            if self.worlds
            and all(w.geometry and w.geometry.status == "computed" for w in self.worlds)
            else "partial"
            if any(w.geometry is not None for w in self.worlds)
            else "not_evaluated"
        )
        if self.assessment != expected_assessment:
            raise ValueError("Metric assessment summary differs from world results")
        unique((world.view_id for world in self.worlds), "metric viewpoints")
        for world in self.worlds:
            unique((str(o.object_number) for o in world.objects), "metric object occurrences")
            unique((link.hotspot_id for link in world.navigation), "metric arrows")
        if self.revision != CanonicalSerializer.digest(
            MetricSpatialContent(worlds=self.worlds, rules=self.rules)
        ):
            raise ValueError("Metric spatial revision does not match its content")
        return self


class EnvironmentSnapshot(Contract):
    contract_family: Literal["pastport-story-inputs"] = "pastport-story-inputs"
    schema_version: Literal["0.1.0"] = "0.1.0"
    project_id: Identifier
    environment_id: Identifier
    import_manifest_sha256: Sha256
    source_pdf_sha256: Sha256
    source_format: Literal["pdf", "idml"] = Field(default="pdf", exclude_if=lambda value: value == "pdf")
    content_revision: Sha256
    spatial_revision: Sha256
    entry_view_id: Identifier
    views: tuple[EnvironmentView, ...]
    objects: tuple[EnvironmentObject, ...]
    positions: tuple[EnvironmentPosition, ...]
    issues: tuple[Text, ...]
    acceptance: Literal["not_inferred"] = "not_inferred"
    spatial_profile: Literal["panorama_positions_only", "metric_3d_source_bound"] = (
        "panorama_positions_only"
    )
    metric_spatial: MetricSpatialSnapshot | None = None

    @model_validator(mode="after")
    def identities(self) -> Self:
        unique((o.stable_id for o in self.objects), "environment stable identities")
        unique((str(o.object_number) for o in self.objects), "environment object numbers")
        unique((v.view_id for v in self.views), "environment viewpoints")
        objects = {o.object_number for o in self.objects}
        views = {v.view_id for v in self.views}
        if (self.metric_spatial is not None) != (self.spatial_profile == "metric_3d_source_bound"):
            raise ValueError("Metric profile and spatial data disagree")
        if self.metric_spatial is not None:
            occurrences = {(p.object_number, p.view_id) for p in self.positions}
            for world in self.metric_spatial.worlds:
                if (
                    world.view_id not in views
                    or (
                        world.interaction_content_revision is not None
                        and world.interaction_content_revision != self.content_revision
                    )
                    or any(
                        o.object_number not in objects
                        or (
                            (o.object_number, world.view_id) not in occurrences
                            and not (o.basis == "saved_anchor" and o.point is not None and o.version > 0)
                        )
                        for o in world.objects
                    )
                    or any(link.target_view_id not in views for link in world.navigation)
                ):
                    raise ValueError("Metric spatial data reference another environment")
        if self.entry_view_id not in views:
            raise ValueError("Entry viewpoint is outside this environment")
        content = EnvironmentContentRevision(objects=self.objects)
        spatial = EnvironmentSpatialRevision(
            entry_view_id=self.entry_view_id, views=self.views, positions=self.positions
        )
        if self.content_revision != CanonicalSerializer.digest(
            content
        ) or self.spatial_revision != CanonicalSerializer.digest(spatial):
            raise ValueError("Environment snapshot revision does not match its content")
        keys = [(p.object_number, p.view_id) for p in self.positions]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate object occurrence in one viewpoint")
        if any(p.object_number not in objects or p.view_id not in views for p in self.positions):
            raise ValueError("Position references an unknown object or viewpoint")
        if any(target not in views for view in self.views for target in view.navigation_targets):
            raise ValueError("Navigation target is outside this environment")
        return self
