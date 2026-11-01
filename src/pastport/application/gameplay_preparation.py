"""Derive supported source-reading mechanics without rewriting authored task meaning."""

import re
from collections.abc import Mapping

from pastport.application.models import ServiceError
from pastport.application.story_authoring import StoryDraftInspector
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.evidence import SourceIndexDraft
from pastport.domain.game import InspectTask
from pastport.domain.gameplay_preparation import (
    ActivityConfig,
    GameplayBinding,
    GameplayGap,
    GameplayPlan,
    InspectionStation,
    LocalizedCopy,
    PluginIdentity,
    SourceChoiceConfig,
    SourceReading,
    SourceReadingConfig,
    TilingConfig,
    ViewConnections,
)
from pastport.domain.mechanics import GameplayCapabilities
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_inputs import EnvironmentSnapshot
from pastport.ports.gameplay_preparation import GameplayVerifier


class GameplayPreparer:
    def __init__(
        self,
        verifier: GameplayVerifier,
        plugin: PluginIdentity,
        additional_plugins: Mapping[str, PluginIdentity] | None = None,
        *,
        capabilities: GameplayCapabilities,
    ) -> None:
        self.verifier, self.plugin = verifier, plugin
        self.capabilities = capabilities
        self.plugins = {plugin.plugin_id: plugin, **(additional_plugins or {})}

    def prepare(
        self,
        draft: NarrativeDraft,
        narrative_ref: ArtifactRef,
        environment: EnvironmentSnapshot,
        source_index: SourceIndexDraft,
        guidance_sha256: str,
    ) -> GameplayPlan:
        if (
            narrative_ref.kind != "narrative"
            or narrative_ref.sha256 != CanonicalSerializer.digest(draft.package)
            or narrative_ref.project_id != draft.package.project_id
            or environment.project_id != draft.package.project_id
            or source_index.project_id != draft.package.project_id
            or self.plugin.plugin_id != "pastport.activity.dialogue"
            or self.plugin.host_profile != "pastport.demo.activities/1"
        ):
            raise ServiceError(
                "GAMEPLAY_INPUT_MISMATCH", "Story, environment or host identity differs"
            )
        if draft.capability_catalog_sha256 != self.capabilities.sha256:
            raise ServiceError("GAMEPLAY_CATALOG_STALE", "Story used another capability catalog")
        spatial_issues = StoryDraftInspector().spatial_issues(draft, environment)
        if spatial_issues:
            raise ServiceError("STORY_SPATIAL_INVALID", "; ".join(spatial_issues))
        intents = {intent.task_id: intent for intent in draft.spatial_intents}
        mechanics = {intent.task_id: intent for intent in draft.gameplay_intents}
        tiling = {intent.task_id: intent for intent in draft.tiling_intents}
        task_ids = {t.task_id for s in draft.package.game.scenes for t in s.tasks}
        if len(tiling) != len(draft.tiling_intents) or not set(tiling) <= task_ids:
            raise ServiceError(
                "GAMEPLAY_INTENT_INVALID", "Duplicate or foreign tiling task identity"
            )
        claims = {claim.claim_id: claim for claim in source_index.candidate_claims}
        bindings: list[GameplayBinding] = []
        gaps: list[GameplayGap] = []
        worlds = environment.metric_spatial.worlds if environment.metric_spatial else ()
        for scene in draft.package.game.scenes:
            for task in scene.tasks:
                if not isinstance(task, InspectTask) or task.guard is not None:
                    gaps.append(
                        GameplayGap(
                            task_id=task.task_id,
                            code="unsupported_task",
                            reason="Only native unguarded linked-source inspection "
                            "has a registered adapter",
                        )
                    )
                    continue
                match = re.fullmatch(r"object-(\d+)", task.asset_id)
                obj = next(
                    (o for o in environment.objects if match and o.object_number == int(match[1])),
                    None,
                )
                if (
                    obj is None
                    or obj.proposal_state == "invalid_structural_relation"
                    or not set(task.evidence_refs) <= claims.keys()
                    or {spot.spot_id for spot in task.spots} != {"result"}
                    or set(task.required_spot_ids) != {"result"}
                ):
                    gaps.append(
                        GameplayGap(
                            task_id=task.task_id,
                            code="missing_source",
                            reason="Task source/object or native inspect result "
                            "semantics are not supported",
                        )
                    )
                    continue
                stations: list[InspectionStation] = []
                for world in worlds:
                    if (
                        not world.geometry
                        or not world.geometry.result
                        or not world.geometry.result.spawn_ground
                    ):
                        continue
                    node = next(
                        (
                            n
                            for n in world.geometry.result.objects
                            if n.key == f"object:{obj.object_number}"
                        ),
                        None,
                    )
                    if node and "inspect" in node.planning.enabled_interactions:
                        station = next(
                            (
                                p
                                for p in node.planning.observation_positions
                                if p.station == "spawn"
                            ),
                            None,
                        )
                        if station:
                            stations.append(
                                InspectionStation(
                                    view_id=world.view_id,
                                    world_id=world.world_id,
                                    point=station.point,
                                    calibration_confirmed=world.calibration.confirmed,
                                    world_binding=world.world_binding,
                                    geometry_input_sha256=world.geometry.input_sha256,
                                    geometry_algorithm_sha256=world.geometry.algorithm_sha256,
                                )
                            )
                if not stations:
                    gaps.append(
                        GameplayGap(
                            task_id=task.task_id,
                            code="missing_station",
                            reason="No registered station supports linked-source "
                            "inspection; visibility is not inferred",
                        )
                    )
                    continue
                config: ActivityConfig = SourceReadingConfig(
                    items=tuple(
                        SourceReading(
                            id=claim_id,
                            text=LocalizedCopy(zh=claims[claim_id].text, en=claims[claim_id].text),
                        )
                        for claim_id in task.evidence_refs
                    )
                )
                requested = mechanics[task.task_id]
                declared = self.capabilities.profile(requested.capability_id)
                if declared is None or (
                    requested.kind == "source_reading"
                    and declared.plugin_id != self.plugin.plugin_id
                ):
                    gaps.append(
                        GameplayGap(
                            task_id=task.task_id,
                            code="unsupported_task",
                            reason="No verified adapter supports the explicit task capability",
                        )
                    )
                    continue
                plugin = self.plugin
                exercise = tiling.get(task.task_id)
                if exercise is not None:
                    selected = self.plugins.get("pastport.activity.tiling")
                    if selected is None:
                        gaps.append(
                            GameplayGap(
                                task_id=task.task_id,
                                code="unsupported_task",
                                reason="Tiling requested but no registered "
                                "tiling plugin is available",
                            )
                        )
                        continue
                    capability = self.capabilities.profile(exercise.capability_id)
                    requirement = exercise.source_requirement
                    if (
                        capability is None
                        or capability.plugin_id != selected.plugin_id
                        or not capability.accepts(exercise.rules)
                        or requirement.target_claim_id != f"claim-object-{obj.object_number}"
                        or requirement.target_claim_id not in task.evidence_refs
                        or any(
                            claim_id not in claims for claim_id in requirement.contrast_claim_ids
                        )
                    ):
                        gaps.append(
                            GameplayGap(
                                task_id=task.task_id,
                                code="unsupported_task",
                                reason="Task requirements exceed verified capability "
                                "or source grounding",
                            )
                        )
                        continue
                    plugin = selected
                    config = TilingConfig(
                        **exercise.rules.model_dump(),
                        source_gate=SourceChoiceConfig(
                            target_claim_id=requirement.target_claim_id,
                            options=tuple(
                                SourceReading(
                                    id=claim_id,
                                    text=LocalizedCopy(
                                        zh=claims[claim_id].text, en=claims[claim_id].text
                                    ),
                                )
                                for claim_id in (
                                    *requirement.contrast_claim_ids,
                                    requirement.target_claim_id,
                                )
                            ),
                        ),
                    )
                try:
                    receipt = self.verifier.verify(config)
                except ServiceError as error:
                    gaps.append(
                        GameplayGap(
                            task_id=task.task_id, code="plugin_validation", reason=str(error)
                        )
                    )
                    continue
                if (
                    receipt.config_sha256 != CanonicalSerializer.digest(config)
                    or receipt.plugin_code_sha256 != plugin.code_sha256
                ):
                    raise ServiceError(
                        "GAMEPLAY_RECEIPT_MISMATCH",
                        "Lifecycle receipt belongs to another plugin or configuration",
                    )
                bindings.append(
                    GameplayBinding(
                        task_id=task.task_id,
                        scene_id=scene.scene_id,
                        object_number=obj.object_number,
                        source_claim_ids=task.evidence_refs,
                        plugin=plugin,
                        config=config,
                        config_sha256=receipt.config_sha256,
                        lifecycle=receipt,
                        completion="board_coverage"
                        if exercise
                        else "source_exposure_not_comprehension",
                        exercise_notice=exercise.fiction_notice if exercise else None,
                        exercise_goal=exercise.learning_goal if exercise else None,
                        capability_id=exercise.capability_id if exercise else "source-reading:1",
                        spatial_candidates=tuple(stations),
                        selected_station=next(
                            station
                            for station in stations
                            if station.view_id == intents[task.task_id].view_id
                            and station.station_id == intents[task.task_id].station_id
                        ),
                    )
                )
        return GameplayPlan(
            project_id=draft.package.project_id,
            narrative_ref=narrative_ref,
            environment_sha256=CanonicalSerializer.digest(environment),
            story_draft_sha256=CanonicalSerializer.digest(draft),
            source_index_sha256=CanonicalSerializer.digest(source_index),
            guidance_sha256=guidance_sha256,
            capability_catalog_sha256=self.capabilities.sha256,
            status="blocked" if gaps else "prepared",
            bindings=tuple(bindings),
            gaps=tuple(gaps),
            navigation=tuple(
                ViewConnections(view_id=w.view_id, links=w.navigation) for w in worlds
            ),
            unresolved=(
                "Mechanics prepared only; presentation must bind "
                "exact views and validate ordered navigation.",
                "Source reading confirms exposure only, not "
                "comprehension, touch, legibility or historical "
                "approval.",
                "Source quotes are preserved as supplied; "
                "duplicated locale text is not a new translation.",
                "Local Demo Activity host only; no production "
                "plugin host or coding worker is certified.",
                *draft.unresolved_items,
            ),
        )
