"""Bounded scene inventory, persistent identity reconciliation and all-view reinspection."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from pastport_pdf_vr.application.projection import angular_distance, pixel_to_sphere
from pastport_pdf_vr.domain.geometry import AnchorPosition, SphericalPoint
from pastport_pdf_vr.domain.recognition import (
    PanoramaView,
    RecognitionResult,
    SceneInspection,
    SceneInspectionRequest,
    ViewDisposition,
)
from pastport_pdf_vr.ports.identity import SceneRepository
from pastport_pdf_vr.ports.semantics import SceneInspector


class RecognitionValidationError(ValueError):
    """Model output changed its allowed image, entity or execution binding."""


@dataclass(frozen=True, slots=True)
class _Candidate:
    state: str
    point: SphericalPoint | None
    image_id: str | None
    basis: tuple[str, ...]


class SceneRecognitionService:
    def __init__(self, repository: SceneRepository, inspector: SceneInspector) -> None:
        self._repository, self._inspector = repository, inspector

    def run(
        self,
        project_id: str,
        input_binding: str,
        views: tuple[PanoramaView, ...],
        grant_ref: str,
        prompt_version: str,
        policy_version: str,
        max_calls: int,
        confirmed_absent: frozenset[str] = frozenset(),
        *,
        model_id: str,
    ) -> RecognitionResult:
        if not 1 <= len(views) <= 100 or len({view.view_id for view in views}) != len(views):
            raise RecognitionValidationError("Views must be nonempty and uniquely identified")
        if any(view.panorama.project_id != project_id for view in views):
            raise RecognitionValidationError("Scene view belongs to another project")
        if not input_binding.strip() or not 1 <= max_calls <= 10_000:
            raise RecognitionValidationError("Input binding and finite call cap are required")
        if not confirmed_absent <= {
            entity.object_id for entity in self._repository.list_entities(project_id)
        }:
            raise RecognitionValidationError("Confirmed absence references an unknown scene entity")
        calls = 0
        gaps: list[str] = []
        observations: dict[tuple[str, str], list[_Candidate]] = defaultdict(list)
        rechecked: set[tuple[str, str]] = set()

        def inspect(request: SceneInspectionRequest) -> tuple[SceneInspection, str] | None:
            nonlocal calls
            # The caller's binding includes the immutable input/config/catalog revision.
            bound = (
                input_binding,
                request.view_id,
                request.phase,
                prompt_version,
                policy_version,
                model_id,
                [image.model_dump(mode="json") for image in request.images],
                request.target_ids,
            )
            binding = hashlib.sha256(
                json.dumps(bound, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            result = self._repository.load_inspection(project_id, binding)
            if result is None:
                if calls >= max_calls:
                    gaps.append(f"call_budget_exhausted:{request.view_id}:{request.phase}")
                    return None
                calls += 1  # A dispatch attempt consumes its slot even if transport raises.
                result = self._inspector.inspect(request)
                self.validate_inspection(request, result)
                self._repository.save_inspection(project_id, binding, result)
            else:
                self.validate_inspection(request, result)
            return result, binding

        for view in views:
            overview = tuple(image for image in view.images if image.inspection_level == "overview")
            if not overview:
                gaps.append(f"overview_images_missing:{view.view_id}")
                continue
            for images in _batches(overview, 8):
                request = SceneInspectionRequest(
                    project_id=project_id,
                    view_id=view.view_id,
                    phase="initial",
                    images=images,
                    catalog=self._repository.list_entities(project_id),
                    grant_ref=grant_ref,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    policy_version=policy_version,
                )
                inspected = inspect(request)
                if inspected is None:
                    continue
                result, binding = inspected
                aliases = self._repository.resolve_proposals(project_id, binding, result.entities)
                mapping = {entity.object_id: entity.object_id for entity in request.catalog}
                mapping.update({alias: entity.object_id for alias, entity in aliases.items()})
                self._collect(request, result, mapping, observations)

        entities = self._repository.list_entities(project_id)
        for view in views:
            missing = tuple(
                entity.object_id
                for entity in entities
                if entity.object_id not in confirmed_absent
                and self._summarize(
                    entity.object_id, view, observations[(entity.object_id, view.view_id)], False
                ).state
                != "located"
            )
            details = tuple(image for image in view.images if image.inspection_level == "detail")
            if missing and not details:
                gaps.append(f"detail_images_missing:{view.view_id}")
                continue
            # One focused recheck round; image and target batches stay bounded.
            for targets in _batches(missing, 100):
                for images in _batches(details, 8):
                    request = SceneInspectionRequest(
                        project_id=project_id,
                        view_id=view.view_id,
                        phase="recheck",
                        images=images,
                        catalog=entities,
                        target_ids=targets,
                        grant_ref=grant_ref,
                        model_id=model_id,
                        prompt_version=prompt_version,
                        policy_version=policy_version,
                    )
                    inspected = inspect(request)
                    for target in targets:
                        key = (target, view.view_id)
                        if key not in rechecked:
                            observations[key] = []
                    if inspected is None:
                        for target in targets:
                            observations[(target, view.view_id)].append(
                                _Candidate(
                                    "not_inspected",
                                    None,
                                    None,
                                    ("Recheck call was not dispatched",),
                                )
                            )
                            rechecked.add((target, view.view_id))
                        continue
                    result, _ = inspected
                    mapping = {entity.object_id: entity.object_id for entity in entities}
                    self._collect(request, result, mapping, observations)
                    reported = {sighting.target_ref for sighting in result.sightings}
                    for target in targets:
                        rechecked.add((target, view.view_id))
                        if target not in reported:
                            observations[(target, view.view_id)].append(
                                _Candidate(
                                    "not_inspected",
                                    None,
                                    None,
                                    ("Model omitted this requested target",),
                                )
                            )
        dispositions: list[ViewDisposition] = []
        for entity in entities:
            for view in views:
                key = (entity.object_id, view.view_id)
                if entity.object_id in confirmed_absent:
                    dispositions.append(
                        ViewDisposition(
                            object_id=entity.object_id,
                            view_id=view.view_id,
                            panorama=view.panorama,
                            panorama_revision=view.panorama_revision,
                            state="confirmed_absent",
                            basis=("Explicitly supplied human-confirmed absence",),
                        )
                    )
                else:
                    dispositions.append(
                        self._summarize(entity.object_id, view, observations[key], key in rechecked)
                    )
        return RecognitionResult(
            entities=entities,
            dispositions=tuple(dispositions),
            calls_used=calls,
            gaps=tuple(dict.fromkeys(gaps)),
        )

    @staticmethod
    def validate_inspection(request: SceneInspectionRequest, result: SceneInspection) -> None:
        local_ids = [proposal.proposal_id for proposal in result.entities]
        known_ids = {entity.object_id for entity in request.catalog}
        if len(set(local_ids)) != len(local_ids) or set(local_ids) & known_ids:
            raise RecognitionValidationError(
                "Proposal identities are duplicated or collide with persistent IDs"
            )
        if request.phase == "recheck" and result.entities:
            raise RecognitionValidationError(
                "Focused recheck cannot create or merge scene identities"
            )
        for proposal in result.entities:
            if proposal.existing_object_id and proposal.existing_object_id not in known_ids:
                raise RecognitionValidationError(
                    "Cross-view identity is outside the supplied catalog"
                )
            if proposal.parent_ref and proposal.parent_ref not in known_ids | set(local_ids):
                raise RecognitionValidationError("Containment references an unknown scene target")
        allowed = (
            set(request.target_ids) if request.phase == "recheck" else known_ids | set(local_ids)
        )
        images = {image.image_id: image for image in request.images}
        for sighting in result.sightings:
            if sighting.target_ref not in allowed or sighting.image_id not in images:
                raise RecognitionValidationError(
                    "Sighting changed its target or allowed image binding"
                )
            image = images[sighting.image_id]
            if sighting.region and (
                sighting.region.bottom_right.x > image.transform.image_width
                or sighting.region.bottom_right.y > image.transform.image_height
            ):
                raise RecognitionValidationError("Sighting region exceeds its matching image")

    @staticmethod
    def _collect(
        request: SceneInspectionRequest,
        result: SceneInspection,
        mapping: dict[str, str],
        observations: dict[tuple[str, str], list[_Candidate]],
    ) -> None:
        images = {image.image_id: image for image in request.images}
        for sighting in result.sightings:
            state: str = (
                sighting.disposition if sighting.role == "environment" else "screen_content"
            )
            point = (
                pixel_to_sphere(sighting.point, images[sighting.image_id].transform)
                if state == "located" and sighting.point
                else None
            )
            if point and abs(point.pitch) > 85:
                state, point = "outside_anchor_range", None
            observations[(mapping[sighting.target_ref], request.view_id)].append(
                _Candidate(
                    state,
                    point,
                    sighting.image_id,
                    sighting.basis,
                )
            )

    @staticmethod
    def _summarize(
        object_id: str, view: PanoramaView, candidates: list[_Candidate], rechecked: bool
    ) -> ViewDisposition:
        located = [candidate for candidate in candidates if candidate.point]
        states = {candidate.state for candidate in candidates}
        position: AnchorPosition | None = None
        state: str
        if "ambiguous_identity" in states:
            state = "ambiguous_identity"
        elif located:
            points = [candidate.point for candidate in located if candidate.point is not None]
            # Seams can duplicate one sighting. Distant alternatives are placement ambiguity,
            # never permission to split a physical entity or average unrelated positions.
            if any(angular_distance(first, second) > 1.0 for first in points for second in points):
                state = "ambiguous_position"
            else:
                first = sorted(located, key=lambda item: item.image_id or "")[0].point
                assert first is not None
                position = AnchorPosition(yaw=first.yaw, pitch=first.pitch)
                state = "located"
        elif not candidates or "not_inspected" in states:
            state = "not_inspected"
        elif states == {"not_seen"}:
            state = "not_seen_after_review" if rechecked else "not_inspected"
        else:
            state = next(
                key
                for key in (
                    "occluded",
                    "insufficient_resolution",
                    "screen_content",
                    "outside_anchor_range",
                )
                if key in states
            )
        return ViewDisposition.model_validate(
            {
                "object_id": object_id,
                "view_id": view.view_id,
                "panorama": view.panorama,
                "panorama_revision": view.panorama_revision,
                "state": state,
                "position": position,
                "image_ids": tuple(dict.fromkeys(c.image_id for c in candidates if c.image_id)),
                "basis": tuple(dict.fromkeys(reason for c in candidates for reason in c.basis)),
                "rechecked": rechecked,
            }
        )


def _batches[T](items: Sequence[T], size: int) -> tuple[tuple[T, ...], ...]:
    return tuple(tuple(items[start : start + size]) for start in range(0, len(items), size))
