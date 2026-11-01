"""Source-bound advisory geometry evidence, independent of narrative permissions."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_matched_environment.domain.models import DomainModel
from pastport_matched_environment.domain.scene3d import Point3D


class SpatialProbeNode(DomainModel):
    key: Annotated[str, Field(min_length=1, max_length=180)]
    point: Point3D | None
    interactions: tuple[Literal["inspect", "navigate"], ...] = ()


class SpatialProbeRequest(DomainModel):
    origin: Point3D
    metric_scale_factor: Annotated[float, Field(gt=0, le=10000, allow_inf_nan=False)]
    ground_plane_offset: Annotated[float, Field(allow_inf_nan=False)]
    nodes: Annotated[tuple[SpatialProbeNode, ...], Field(max_length=100)]


RouteStatus = Literal[
    "clear", "distance_limit", "ground_unknown", "direct_obstructed", "missing_position"
]


class SpatialObservationPosition(DomainModel):
    station: str
    point: Point3D
    distance: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    sight: Literal["clear_to_anchor", "collider_occluded", "target_too_close"]


class SpatialPlanningFacts(DomainModel):
    basis: Literal["registered_geometry_not_identity_approval"]
    observation_positions: tuple[SpatialObservationPosition, ...]
    approach_station: str | None
    enabled_interactions: tuple[Literal["inspect", "navigate"], ...]
    detail_reading: Literal["task_specific_requirement_missing"]
    physical_touch: Literal["host_touch_rule_not_registered"]


class SpatialProbeObject(DomainModel):
    key: str
    route_status: RouteStatus
    route: tuple[Point3D, ...]
    sight: Literal["clear_to_anchor", "collider_occluded", "target_too_close", "missing_position"]
    distance: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None
    legibility: Literal["unknown"]
    touch: Literal["unknown"]
    planning: SpatialPlanningFacts


class SpatialProbeRoute(DomainModel):
    source: str
    target: str
    status: RouteStatus
    points: tuple[Point3D, ...]


class SpatialProbeResult(DomainModel):
    policy_version: Literal["pastport.geometry-direct/1"]
    spawn_ground: bool
    spawn: Point3D
    eye_height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    objects: tuple[SpatialProbeObject, ...]
    routes: tuple[SpatialProbeRoute, ...]
