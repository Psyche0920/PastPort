"""Version-bound mechanical comparison; uncertainty never grants human approval."""

from typing import Literal

from pydantic import JsonValue

from pastport.application.models import Actor, RunRecord, ServiceError
from pastport.application.service import EditorialService
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract, Text
from pastport.domain.modules import ChangeImpactReport, NarrativeDraft
from pastport.domain.packages import ReviewTarget
from pastport.workflow.stages import StageRunner


class CompareChanges(Contract):
    before_ref: ArtifactRef
    after_ref: ArtifactRef


class FieldChange(Contract):
    json_pointer: str
    before: JsonValue
    after: JsonValue


class ChangeImpactView(Contract):
    before_ref: ArtifactRef
    after_ref: ArtifactRef
    status: Literal["complete", "uncertain", "unavailable"]
    report: ChangeImpactReport | None
    reason: Text
    differences: tuple[FieldChange, ...] = ()
    truncated: bool = False


class ChangeImpactService:
    def __init__(self, service: EditorialService, stages: StageRunner) -> None:
        self.service = service
        self.stages = stages

    @staticmethod
    def draft(run: RunRecord, reference: ArtifactRef) -> NarrativeDraft:
        item = next((item for item in run.artifacts if item.reference == reference), None)
        if item is None or reference.artifact_id != run.state.run_id + ":draft":
            raise ServiceError(
                "ARTIFACT_NOT_FOUND",
                "Comparison requires exact draft references from this run",
                404,
            )
        value = NarrativeDraft.model_validate_json(item.payload_json)
        if CanonicalSerializer.digest(value) != reference.sha256:
            raise ServiceError("ARTIFACT_CHANGED", "Comparison draft failed its hash")
        return value

    @staticmethod
    def differences(
        before: JsonValue, after: JsonValue, path: str = ""
    ) -> tuple[tuple[FieldChange, ...], bool]:
        changes: list[FieldChange] = []
        truncated = False

        def visit(left: JsonValue, right: JsonValue, pointer: str) -> None:
            nonlocal truncated
            if not isinstance(left, (dict, list)) and left == right and type(left) is type(right):
                return
            if len(changes) >= 200:
                truncated = True
                return
            if isinstance(left, dict) and isinstance(right, dict):
                for key in sorted(set(left) | set(right)):
                    key_pointer = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                    if (key in left) != (key in right):
                        if len(changes) >= 200:
                            truncated = True
                        else:
                            changes.append(
                                FieldChange(
                                    json_pointer=key_pointer,
                                    before=left.get(key),
                                    after=right.get(key),
                                )
                            )
                    else:
                        visit(left[key], right[key], key_pointer)
            elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
                for index, (old, new) in enumerate(zip(left, right, strict=True)):
                    visit(old, new, pointer + "/" + str(index))
            else:
                changes.append(FieldChange(json_pointer=pointer, before=left, after=right))

        visit(before, after, path)
        return tuple(changes), truncated

    def compare(self, actor: Actor, run_id: str, request: CompareChanges) -> ChangeImpactView:
        run = self.service.run(run_id, actor)
        before = self.draft(run, request.before_ref)
        after = self.draft(run, request.after_ref)
        current = next(
            item.reference
            for item in reversed(run.artifacts)
            if item.reference.artifact_id.endswith(":draft")
        )
        if request.after_ref != current:
            raise ServiceError("STATE_STALE", "Comparison target is no longer the current draft")
        differences, truncated = self.differences(
            before.model_dump(mode="json"), after.model_dump(mode="json")
        )
        # Limit this conclusion to observable target identity, never semantic correctness.
        targets: list[ReviewTarget] = []
        for gate in ("evidence", "narrative", "publication"):
            if any(review.gate == gate for review in run.review_requests):
                targets.extend(self.stages.review_targets(run, gate))
        revoked = set(self.service.database.revoked_reviews(run_id))
        reusable = []
        invalidated = []
        for decision in run.review_decisions:
            if decision.decision_id in revoked or decision.decision != "approved":
                continue
            matching = any(
                (target.target_id, target.version, target.sha256, target.gate)
                == (
                    decision.target_id,
                    decision.target_version,
                    decision.target_hash,
                    decision.gate,
                )
                for target in targets
            )
            if not matching:
                invalidated.append(decision.decision_id)
                continue
            try:
                self.stages.authority.decision(decision, run.state.project_id)
            except ServiceError:
                # No current authority means no reusable approval, even if content did not change.
                invalidated.append(decision.decision_id)
            else:
                reusable.append(decision.decision_id)
        scenes = tuple(
            sorted(
                {
                    scene.scene_id
                    for scene in (*before.package.game.scenes, *after.package.game.scenes)
                }
            )
        )
        reason = (
            "Mechanical differences and current approval bindings are verified. "
            "Semantic dependency impact requires human review; "
            "all scenes are included conservatively."
        )
        report = ChangeImpactReport(
            before_ref=request.before_ref,
            after_ref=request.after_ref,
            changed_ids=scenes if differences else (),
            change_kinds=("character_causality", "rule", "translation") if differences else (),
            affected_scene_ids=scenes if differences else (),
            invalidated_decision_ids=tuple(sorted(set(invalidated))),
            reusable_decision_ids=tuple(sorted(set(reusable))),
            reason=reason,
            analysis_status="uncertain",
        )
        return ChangeImpactView(
            before_ref=request.before_ref,
            after_ref=request.after_ref,
            status="uncertain",
            report=report,
            reason=reason,
            differences=differences,
            truncated=truncated,
        )
