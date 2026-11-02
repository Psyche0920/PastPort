"""Revalidate declared story dependencies and materialize a separately bound reuse run."""

import hashlib
import re
import shutil
from pathlib import Path

from pastport.adapters.gameplay_catalog import load_gameplay_catalog
from pastport.adapters.gameplay_verifier import DemoGameplayVerifier
from pastport.adapters.runtime_resources import runtime_root, skill_root
from pastport.adapters.story_materials import StoryMaterialReader
from pastport.application.gameplay_preparation import GameplayPreparer
from pastport.application.models import ServiceError
from pastport.application.story_authoring import (
    StoryAuthoringCheck,
    StoryDraftInspector,
    StoryInputLock,
)
from pastport.domain.common import CanonicalSerializer
from pastport.domain.evidence import SourceIndexDraft
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_inputs import EnvironmentSnapshot
from pastport.domain.story_reuse import (
    StoryIntroductionChange,
    StoryReuseDecision,
    StoryReuseReport,
)


class StoryReuseAdapter:
    @staticmethod
    def report(path: Path, value: StoryReuseReport) -> None:
        path.write_text(
            value.model_copy(update={"compatibility_version": 1}).model_dump_json(indent=2)
        )

    def prepare(
        self,
        previous: GameMakingRequest,
        current: GameMakingRequest,
        output: Path,
        *,
        decision: StoryReuseDecision | None = None,
    ) -> GameMakingRequest:
        parent = previous.saved_story_run
        report_path = output / "story-compatibility.json"
        required = (
            "input-lock.json",
            "narrative-draft.json",
            "story-check.json",
            "budget.json",
            "environment-input.json",
            "source-index.json",
        )
        if not all((parent / name).is_file() for name in required):
            self.report(
                report_path,
                StoryReuseReport(status="missing", issues=("此资料来源尚无已校验的旧故事。",)),
            )
            return current
        issues: list[str] = []
        changed_introductions: list[StoryIntroductionChange] = []
        try:
            draft_bytes = (parent / "narrative-draft.json").read_bytes()
            draft = NarrativeDraft.model_validate_json(draft_bytes)
            old_check = StoryAuthoringCheck.model_validate_json(
                (parent / "story-check.json").read_bytes()
            )
            old_lock = StoryInputLock.model_validate_json((parent / "input-lock.json").read_bytes())
            old_environment = (parent / "environment-input.json").read_bytes()
            old = EnvironmentSnapshot.model_validate_json(old_environment)
            old_index = SourceIndexDraft.model_validate_json(
                (parent / "source-index.json").read_bytes()
            )
            current_materials = StoryMaterialReader().read(
                current.original_pdf,
                current.source_document,
                current.environment,
                current.media_directory,
            )
            catalog = load_gameplay_catalog()
            spatial_only_repair = bool(
                old_check.status == "invalid" and old_check.issues
                and all(re.fullmatch(r"Task [A-Za-z0-9_.:-]+ (?:has an invalid spatial intent|has no registered source-inspection station)", issue) for issue in old_check.issues)
                and old.metric_spatial and current_materials.museum.metric_spatial
                and any(world.geometry is None or world.geometry.result is None for world in old.metric_spatial.worlds)
                and all(world.geometry and world.geometry.result for world in current_materials.museum.metric_spatial.worlds)
            )
            if (
                (old_check.status != "ready" and not spatial_only_repair)
                or old_check.story_draft_sha256 != CanonicalSerializer.digest(draft)
                or old_check.narrative_sha256 != CanonicalSerializer.digest(draft.package)
                or old_lock.environment_sha256 != hashlib.sha256(old_environment).hexdigest()
                or old_lock.source_index_sha256 != CanonicalSerializer.digest(old_index)
            ):
                issues.append("旧故事的校验或环境锁已失效，不能作为兼容基线。")
            if (
                old.project_id != current_materials.museum.project_id
                or old_lock.original_pdf_sha256 != current_materials.original_pdf_sha256
                or old.import_manifest_sha256 != current_materials.museum.import_manifest_sha256
            ):
                issues.append("史料、匹配导入或项目来源不同，不能跨项目套用故事。")
            original = {o.object_number: o for o in old.objects}
            objects = {o.object_number: o for o in current_materials.museum.objects}
            dependencies: dict[str, set[int]] = {
                intent.task_id: {intent.object_number} for intent in draft.spatial_intents
            }
            references: dict[str, list[str]] = {}
            for scene in draft.package.game.scenes:
                for task in scene.tasks:
                    references.setdefault(task.task_id, []).extend(task.evidence_refs)
            for author_report in draft.authoring_report:
                references.setdefault(author_report.task_id, []).extend(
                    (*author_report.heritage_refs, *author_report.premise_source_ids)
                )
            for exercise in draft.tiling_intents:
                references.setdefault(exercise.task_id, []).extend(
                    (
                        exercise.source_requirement.target_claim_id,
                        *exercise.source_requirement.contrast_claim_ids,
                    )
                )
            for task_id, keys in references.items():
                for key in keys:
                    match = re.fullmatch(r"(?:claim-)?object-([1-9][0-9]*)", key)
                    if match:
                        dependencies.setdefault(task_id, set()).add(int(match[1]))
                    for obj in old.objects:
                        if key in (obj.stable_id, obj.historical_id):
                            dependencies.setdefault(task_id, set()).add(obj.object_number)
            for task_id, numbers in dependencies.items():
                for number in numbers:
                    before, after = original.get(number), objects.get(number)
                    if before is None or after is None:
                        issues.append(f"任务 {task_id}：所用物件 {number} 已缺失。")
                        continue
                    if (before.stable_id, before.historical_id, before.quote) != (
                        after.stable_id,
                        after.historical_id,
                        after.quote,
                    ):
                        issues.append(
                            f"任务 {task_id}：物件 {number} 对应或引用史料已变化，"
                            "需核对该任务依据。"
                        )
                    if before.introduction != after.introduction:
                        changed_introductions.append(
                            StoryIntroductionChange(
                                task_id=task_id,
                                object_number=number,
                                before=before.introduction,
                                after=after.introduction,
                            )
                        )
            check = StoryDraftInspector().inspect(
                draft,
                current_materials.museum,
                frozenset(c.claim_id for c in current_materials.index.candidate_claims),
                frozenset(s.source_id for s in current_materials.index.sources),
                require_spatial_intents=True,
                expected_catalog_sha256=catalog.sha256,
                capabilities=catalog,
            )
            issues.extend(check.issues)
            if issues:
                self.report(
                    report_path,
                    StoryReuseReport(
                        status="incompatible",
                        issues=tuple(dict.fromkeys(issues)),
                        parent_story_run=parent,
                        parent_draft_sha256=hashlib.sha256(draft_bytes).hexdigest(),
                    ),
                )
                return current
            verifier = DemoGameplayVerifier(runtime_root())
            gameplay = GameplayPreparer(
                verifier,
                verifier.identity(),
                {"pastport.activity.tiling": verifier.identity("tiling")},
                capabilities=catalog,
            ).prepare(
                draft,
                CanonicalSerializer.reference(draft.package, "reuse-compatibility", "narrative"),
                current_materials.museum,
                current_materials.index,
                hashlib.sha256(
                    (skill_root() / "gameplay-preparation/SKILL.md").read_bytes()
                ).hexdigest(),
            )
            if gameplay.status != "prepared":
                gaps = tuple(f"任务 {gap.task_id}：{gap.reason}" for gap in gameplay.gaps)
                self.report(
                    report_path,
                    StoryReuseReport(
                        status="incompatible",
                        issues=gaps,
                        parent_story_run=parent,
                        parent_draft_sha256=hashlib.sha256(draft_bytes).hexdigest(),
                    ),
                )
                return current
            changes = tuple(
                sorted(
                    changed_introductions, key=lambda change: (change.task_id, change.object_number)
                )
            )
            if changes and decision is None:
                self.report(
                    report_path,
                    StoryReuseReport(
                        status="needs_confirmation",
                        issues=tuple(
                            f"任务 {change.task_id} 使用的 {change.object_number} 号介绍有改动。"
                            for change in changes
                        ),
                        introduction_changes=changes,
                        parent_story_run=parent,
                        parent_draft_sha256=hashlib.sha256(draft_bytes).hexdigest(),
                        environment_sha256=current_materials.environment_sha256,
                        source_index_sha256=CanonicalSerializer.digest(current_materials.index),
                        capability_catalog_sha256=catalog.sha256,
                    ),
                )
                return current
            if decision is not None and (
                decision.environment_sha256 != current_materials.environment_sha256
                or decision.parent_draft_sha256 != hashlib.sha256(draft_bytes).hexdigest()
                or decision.introduction_changes != changes
            ):
                raise ServiceError(
                    "STORY_CONFIRMATION_STALE", "资料或故事已变化，请重新检查并确认。", 409
                )
            target = current.saved_story_run
            if not target.resolve().is_relative_to(output.resolve()) or (
                target.exists() and any(target.iterdir())
            ):
                raise ServiceError(
                    "STORY_REUSE_TARGET_INVALID", "复用记录必须写入独立的空目录。", 409
                )
            target.mkdir(parents=True, exist_ok=True)
            (target / "narrative-draft.json").write_bytes(draft_bytes)
            (target / "environment-input.json").write_bytes(current_materials.environment_bytes)
            (target / "source-index.json").write_text(
                current_materials.index.model_dump_json(indent=2)
            )
            rebound = old_lock.model_copy(
                update={
                    "environment_sha256": current_materials.environment_sha256,
                    "source_document_sha256": current_materials.source_document_sha256,
                    "source_index_sha256": CanonicalSerializer.digest(current_materials.index),
                }
            )
            (target / "input-lock.json").write_text(rebound.model_dump_json(indent=2))
            (target / "story-check.json").write_text(check.model_dump_json(indent=2))
            (target / "story.md").write_text(StoryDraftInspector().readable(draft))
            shutil.copyfile(parent / "budget.json", target / "budget.json")
            report = StoryReuseReport(
                status="compatible",
                issues=(),
                introduction_changes=changes,
                confirmation=decision,
                parent_story_run=parent,
                parent_draft_sha256=hashlib.sha256(draft_bytes).hexdigest(),
                environment_sha256=current_materials.environment_sha256,
                source_index_sha256=CanonicalSerializer.digest(current_materials.index),
                capability_catalog_sha256=catalog.sha256,
            )
            self.report(report_path, report)
            self.report(target / "story-compatibility.json", report)
            return current.model_copy(
                update={"brief": previous.brief, "skills_directory": previous.skills_directory}
            )
        except (OSError, ValueError, ServiceError) as error:
            self.report(
                report_path,
                StoryReuseReport(
                    status="incompatible",
                    issues=(f"旧故事兼容检查未完成：{error}",),
                    parent_story_run=parent,
                ),
            )
            return current

    def verify(self, request: GameMakingRequest) -> None:
        root = request.saved_story_run
        proof = StoryReuseReport.model_validate_json(
            (root / "story-compatibility.json").read_bytes()
        )
        draft = (root / "narrative-draft.json").read_bytes()
        if proof.introduction_changes and (
            proof.confirmation is None
            or proof.confirmation.introduction_changes != proof.introduction_changes
            or proof.confirmation.environment_sha256 != proof.environment_sha256
            or proof.confirmation.parent_draft_sha256 != proof.parent_draft_sha256
        ):
            raise ServiceError("STORY_CONFIRMATION_STALE", "介绍修改没有有效的沿用确认。", 409)
        if (
            proof.status != "compatible"
            or proof.parent_story_run is None
            or proof.parent_draft_sha256 != hashlib.sha256(draft).hexdigest()
            or proof.parent_draft_sha256
            != hashlib.sha256(
                (proof.parent_story_run / "narrative-draft.json").read_bytes()
            ).hexdigest()
            or proof.environment_sha256
            != hashlib.sha256(request.environment.read_bytes()).hexdigest()
            or proof.capability_catalog_sha256 != load_gameplay_catalog().sha256
        ):
            raise ServiceError("STORY_REUSE_STALE", "旧故事兼容记录已失效，请重新检查。", 409)
        material = StoryMaterialReader().read(
            request.original_pdf,
            request.source_document,
            request.environment,
            request.media_directory,
        )
        lock = StoryInputLock.model_validate_json((root / "input-lock.json").read_bytes())
        check = StoryAuthoringCheck.model_validate_json((root / "story-check.json").read_bytes())
        narrative = NarrativeDraft.model_validate_json(draft)
        if (
            hashlib.sha256((root / "environment-input.json").read_bytes()).hexdigest()
            != proof.environment_sha256
            or lock.environment_sha256 != proof.environment_sha256
            or lock.original_pdf_sha256 != material.original_pdf_sha256
            or lock.source_document_sha256 != material.source_document_sha256
            or proof.source_index_sha256 != CanonicalSerializer.digest(material.index)
            or lock.source_index_sha256 != proof.source_index_sha256
            or CanonicalSerializer.digest(
                SourceIndexDraft.model_validate_json((root / "source-index.json").read_bytes())
            )
            != proof.source_index_sha256
            or check.status != "ready"
            or check.story_draft_sha256 != CanonicalSerializer.digest(narrative)
            or check.narrative_sha256 != CanonicalSerializer.digest(narrative.package)
        ):
            raise ServiceError("STORY_REUSE_STALE", "复用的故事、来源或空间版本已变化。", 409)
