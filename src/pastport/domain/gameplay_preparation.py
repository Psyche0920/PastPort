"""Gameplay preparation outputs are plans, never committed Story state or UI code."""

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
from pastport.domain.mechanics import CoverageProblem
from pastport.domain.story_inputs import SpatialNavigationLink, SpatialPoint


class LocalizedCopy(Contract):
    zh: Text | None = None
    en: Text
    tr: Text | None = None

    @model_validator(mode="after")
    def complete_language_pair(self) -> Self:
        if not self.zh and not self.tr:
            raise ValueError("English requires Turkish or legacy Chinese copy")
        return self


class SourceReading(Contract):
    id: Identifier
    speaker: Literal["source"] = "source"
    text: LocalizedCopy


class SourceReadingConfig(Contract):
    kind: Literal["dialogue"] = "dialogue"
    items: Annotated[tuple[SourceReading, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def source_identities(self) -> Self:
        unique((item.id for item in self.items), "source readings")
        return self


class SourceChoiceConfig(Contract):
    target_claim_id: Identifier
    options: Annotated[tuple[SourceReading, ...], Field(min_length=2, max_length=4)]

    @model_validator(mode="after")
    def valid_choices(self) -> Self:
        unique((item.id for item in self.options), "source choice options")
        if self.target_claim_id not in {item.id for item in self.options}:
            raise ValueError("Source choice has no supported answer")
        return self


class CoveragePlacement(Contract):
    id: Annotated[int, Field(ge=0)]
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    rotated: bool


class TilingConfig(CoverageProblem):
    kind: Literal["tiling"] = "tiling"
    source_gate: SourceChoiceConfig | None = None
    failure_policy: Literal["retry_without_story_progress"] = "retry_without_story_progress"
    exit_policy: Literal["preserve_progress"] = "preserve_progress"


ActivityConfig = Annotated[SourceReadingConfig | TilingConfig, Field(discriminator="kind")]


class PluginIdentity(Contract):
    plugin_id: Identifier
    version: Literal["1.0.0"] = "1.0.0"
    host_profile: Literal["pastport.demo.activities/1"] = "pastport.demo.activities/1"
    entrypoint: Text
    code_sha256: Sha256


class LifecycleReceipt(Contract):
    plugin_code_sha256: Sha256
    verifier_sha256: Sha256
    config_sha256: Sha256
    checks: tuple[Text, ...]
    solution: tuple[CoveragePlacement, ...] = ()
    status: Literal["passed"] = "passed"


class InspectionStation(Contract):
    view_id: Identifier
    world_id: Identifier
    station_id: Literal["spawn"] = "spawn"
    point: SpatialPoint
    calibration_confirmed: bool
    interaction: Literal["inspect_linked_source"] = "inspect_linked_source"
    world_binding: Sha256
    geometry_input_sha256: Sha256
    geometry_algorithm_sha256: Sha256


class ViewConnections(Contract):
    view_id: Identifier
    links: tuple[SpatialNavigationLink, ...]


class GameplayBinding(Contract):
    task_id: Identifier
    scene_id: Identifier
    object_number: Annotated[int, Field(ge=1)]
    source_claim_ids: tuple[Identifier, ...]
    plugin: PluginIdentity
    config: ActivityConfig
    config_sha256: Sha256
    lifecycle: LifecycleReceipt
    spatial_candidates: tuple[InspectionStation, ...]
    selected_station: InspectionStation
    completion: Literal["source_exposure_not_comprehension", "board_coverage"] = (
        "source_exposure_not_comprehension"
    )
    exercise_notice: Text | None = None
    exercise_goal: Text | None = None
    capability_id: Identifier = "source-reading:1"
    scene_binding: Literal["pending_presentation"] = "pending_presentation"

    @model_validator(mode="after")
    def exact_receipt(self) -> Self:
        if (
            self.config_sha256 != CanonicalSerializer.digest(self.config)
            or self.lifecycle.config_sha256 != self.config_sha256
            or self.lifecycle.plugin_code_sha256 != self.plugin.code_sha256
            or (
                isinstance(self.config, SourceReadingConfig)
                and (
                    tuple(item.id for item in self.config.items) != self.source_claim_ids
                    or self.completion != "source_exposure_not_comprehension"
                    or self.plugin.plugin_id != "pastport.activity.dialogue"
                )
            )
            or (
                isinstance(self.config, TilingConfig)
                and (
                    self.completion != "board_coverage"
                    or self.exercise_notice is None
                    or self.exercise_goal is None
                    or self.plugin.plugin_id != "pastport.activity.tiling"
                    or self.config.source_gate is None
                    or len(self.lifecycle.solution) != len(self.config.pieces)
                )
            )
            or not self.spatial_candidates
            or self.selected_station not in self.spatial_candidates
        ):
            raise ValueError("Gameplay config, source, station or receipt identity differs")
        return self


class GameplayGap(Contract):
    task_id: Identifier
    code: Literal["unsupported_task", "missing_source", "missing_station", "plugin_validation"]
    reason: Text


class GameplayPlan(Contract):
    schema_version: Literal["gameplay-preparation/0.4.0"] = "gameplay-preparation/0.4.0"
    project_id: Identifier
    narrative_ref: ArtifactRef
    environment_sha256: Sha256
    story_draft_sha256: Sha256
    source_index_sha256: Sha256
    guidance_sha256: Sha256
    capability_catalog_sha256: Sha256
    host_profile: Literal["pastport.demo.activities/1"] = "pastport.demo.activities/1"
    status: Literal["prepared", "blocked"]
    bindings: tuple[GameplayBinding, ...]
    gaps: tuple[GameplayGap, ...]
    navigation: tuple[ViewConnections, ...]
    unresolved: tuple[Text, ...]
    playable: Literal[False] = False
    global_state_committed: Literal[False] = False
    model_calls: Literal[0] = 0

    @model_validator(mode="after")
    def coherent_plan(self) -> Self:
        unique((binding.task_id for binding in self.bindings), "gameplay task bindings")
        if (
            self.narrative_ref.project_id != self.project_id
            or self.narrative_ref.kind != "narrative"
            or (self.status == "prepared") != (not self.gaps)
            or any(binding.plugin.host_profile != self.host_profile for binding in self.bindings)
        ):
            raise ValueError("Gameplay plan status, project or host identity differs")
        return self
