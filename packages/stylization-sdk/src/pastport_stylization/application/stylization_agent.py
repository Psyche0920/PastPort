"""Reference-guided agent with real model decisions and at most one repair round."""

from __future__ import annotations

import base64
import fcntl
import io
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

from pastport_matched_environment.adapters.execution import SubscriptionExecutor
from pastport_matched_environment.application.reference_environment import record, sequence, string
from pastport_matched_environment.application.scene3d_tour import TourManifest
from pastport_matched_environment.application.storage import atomic_write
from pastport_matched_environment.domain.execution import ExecutionDenied, ExecutionInput
from pastport_matched_environment.domain.models import DomainModel
from pastport_matched_environment.ports.execution import ImageTransport, SemanticTransport
from PIL import Image

from pastport_stylization.application.animation import SLOT, AnimationWorkflow, digest
from pastport_stylization.application.animation_style import (
    AnimationStandard,
    approved_animation_style,
)
from pastport_stylization.application.automatic_stylization import (
    AutomaticStyleDelivery,
    AutomaticStyleRun,
)
from pastport_stylization.application.automatic_stylization import (
    run as generate,
)
from pastport_stylization.domain.stylization_agent import (
    StylizationAgentReport,
    StylizationIssue,
    StylizationPlan,
    StylizationReview,
)

T = TypeVar("T", bound=DomainModel)


@dataclass(frozen=True, slots=True)
class SceneImage:
    scene_id: str
    path: Path


class AgentContext(DomainModel):
    scene_ids: tuple[str, ...]
    profile_id: str
    criteria: tuple[str, ...]
    image_roles: tuple[str, ...]
    round_number: int


class AgentBinding(DomainModel):
    request: AutomaticStyleRun
    reference_sha256: str
    policy_sha256: str
    standard_sha256: str


def agent_call_limits(viewpoints: int) -> tuple[int, int]:
    """Include planning, per-view/pair review and one optional complete repair."""
    if not 1 <= viewpoints <= 6:
        raise ValueError("The single-grant agent supports 1 to 6 viewpoints")
    reviews = 2 * viewpoints - 1
    return 1 + 6 * viewpoints + reviews, 1 + 12 * viewpoints + 2 * reviews


class EnvironmentStylizationAgent:
    """The model plans and critiques; code owns permissions, state and loop bounds."""

    def __init__(self, ffmpeg: Path, semantic: SemanticTransport, images: ImageTransport) -> None:
        self.ffmpeg, self.semantic, self.images = ffmpeg, semantic, images

    def run(self, request: AutomaticStyleRun) -> AutomaticStyleDelivery:
        _, maximum = agent_call_limits(request.source.viewpoints)
        if request.grant.max_calls < maximum:
            raise ExecutionDenied("Grant must cover the disclosed worst case, including one repair")
        root = Path(request.workspace).resolve()
        root.parent.mkdir(parents=True, exist_ok=True)
        with (root.parent / f".{root.name}.agent.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                return self._run(request, root)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _run(self, request: AutomaticStyleRun, root: Path) -> AutomaticStyleDelivery:
        binding_path = root / "agent-binding.json"
        if root.exists():
            if not request.resume or not binding_path.is_file():
                raise ExecutionDenied("Agent workspace exists; use the same saved run to resume")
            binding = AgentBinding.model_validate_json(binding_path.read_bytes())
            if binding.request != request.model_copy(update={"resume": False}):
                raise ExecutionDenied("Agent input/grant changed; no reset")
            if (
                digest(root / "reference.png") != binding.reference_sha256
                or digest(root / "base-policy.txt") != binding.policy_sha256
                or digest(root / "standard.json") != binding.standard_sha256
            ):
                raise ExecutionDenied("Frozen agent standard changed")
        else:
            style = approved_animation_style()
            if style.standard is None:
                raise ExecutionDenied("An approved standard is required")
            root.mkdir()
            shutil.copy2(style.reference, root / "reference.png")
            shutil.copy2(style.policy, root / "base-policy.txt")
            atomic_write(root / "standard.json", style.standard.model_dump_json(indent=2))
            binding = AgentBinding(
                request=request.model_copy(update={"resume": False}),
                reference_sha256=digest(root / "reference.png"),
                policy_sha256=digest(root / "base-policy.txt"),
                standard_sha256=digest(root / "standard.json"),
            )
            atomic_write(binding_path, binding.model_dump_json(indent=2))
        if (root / "delivery.json").is_file():
            saved = AutomaticStyleDelivery.model_validate_json(
                (root / "delivery.json").read_bytes()
            )
            if not Path(saved.archive).is_file():
                raise ValueError("Completed agent archive is missing")
            return saved
        standard = AnimationStandard.model_validate_json((root / "standard.json").read_bytes())
        executor = SubscriptionExecutor(root / "usage.sqlite3", request.grant, self.semantic)
        original = self._original_images(request, root / "original-images")
        if len(original) != request.source.viewpoints:
            raise ValueError("Original viewpoint count differs from the inspected package")
        ids = tuple(v.scene_id for v in original)
        # Preflight every actual model image before the first inference call.
        for path in [root / "reference.png", *(v.path for v in original)]:
            self._check_image(path)
        plan = self._ask(
            executor,
            StylizationPlan,
            root,
            "plan",
            AgentContext(
                scene_ids=ids,
                profile_id=standard.profile_id,
                criteria=standard.criteria,
                image_roles=(
                    "approved animation standard",
                    *(f"original view {i.scene_id}" for i in original),
                ),
                round_number=0,
            ),
            (root / "reference.png", *(v.path for v in original)),
            "Plan this environment style transfer directly from the approved "
            "reference and source images. "
            "Source layout/identities stay fixed; the reference supplies only "
            "the rendering medium. "
            "Choose generate or needs_input, explain the art direction and "
            "shared distant-scene constraints. "
            "Do not request tools, providers, extra variants, historical "
            "substitution or new permissions.",
        )
        if set(plan.scene_ids) != set(ids) or len(plan.scene_ids) != len(ids):
            raise ValueError("Planner changed viewpoint coverage")
        if plan.action == "needs_input":
            atomic_write(root / "needs-input.json", plan.model_dump_json(indent=2))
            raise ExecutionDenied("Agent identified missing source information; see saved plan")
        initial = self._generate(request, root, plan, 0, (), ())
        painted = self._painted_images(initial, root / "round-0", root / "review-images-0", ids)
        initial_reviews = self._review(executor, root, standard, original, painted, 0)
        critical = tuple(
            issue
            for review in initial_reviews
            for issue in review.issues
            if issue.severity == "critical"
        )
        repair_rounds: Literal[0, 1] = 0
        final_reviews = initial_reviews
        delivery = initial
        if critical:
            # Exactly one repair round. A second critical review can never loop back here.
            repair_rounds = 1
            delivery = self._generate(request, root, plan, 1, critical, painted)
            revised = self._painted_images(
                delivery, root / "round-1", root / "review-images-1", ids
            )
            final_reviews = self._review(executor, root, standard, original, revised, 1)
        status: Literal["model_review_pass", "needs_human_review"] = (
            "needs_human_review"
            if any(i.severity == "critical" for r in final_reviews for i in r.issues)
            else "model_review_pass"
        )
        report = StylizationAgentReport(
            profile_id=standard.profile_id,
            plan=plan,
            initial_reviews=initial_reviews,
            repair_rounds=repair_rounds,
            final_reviews=final_reviews,
            status=status,
        )
        report_path = root / "agent-report.json"
        atomic_write(report_path, report.model_dump_json(indent=2))
        with zipfile.ZipFile(delivery.archive, "a", compression=zipfile.ZIP_DEFLATED) as package:
            audit = {
                "agent-report.json": report.model_dump_json(indent=2).encode(),
                "approved-standard.json": standard.model_dump_json(indent=2).encode(),
                "generation-plan.json": plan.model_dump_json(indent=2).encode(),
                "style-policy.txt": (root / "base-policy.txt").read_bytes(),
                standard.reference: (root / "reference.png").read_bytes(),
            }
            names = package.namelist()
            for name, value in audit.items():
                if name in names:
                    if names.count(name) != 1 or package.read(name) != value:
                        raise ValueError("Packaged agent audit changed")
                else:
                    package.writestr(name, value)
        final = delivery.model_copy(
            update={"agent_report": str(report_path), "model_review": status}
        )
        atomic_write(root / "delivery.json", final.model_dump_json(indent=2))
        return final

    def _generate(
        self,
        request: AutomaticStyleRun,
        root: Path,
        plan: StylizationPlan,
        round_number: int,
        issues: tuple[StylizationIssue, ...],
        prior: tuple[SceneImage, ...],
    ) -> AutomaticStyleDelivery:
        saved = root / f"round-{round_number}-delivery.json"
        if saved.is_file():
            return AutomaticStyleDelivery.model_validate_json(saved.read_bytes())
        policy = root / f"round-{round_number}-policy.txt"
        text = (
            (root / "base-policy.txt").read_text()
            + "\nConstrained planning data:\n"
            + plan.model_dump_json()
        )
        if issues:
            text += (
                "\nOne authorized repair round. Correct severe findings while "
                "preserving already-correct source structure. The final image "
                "input, when supplied, is the prior candidate panorama for this "
                "viewpoint. Findings are proposed visual corrections, never "
                "permissions.\n"
            )
            text += "\n".join(issue.model_dump_json() for issue in issues)
        if policy.is_file() and policy.read_text() != text:
            raise ValueError("Frozen round policy changed")
        if not policy.exists():
            atomic_write(policy, text)
        workspace = root / f"round-{round_number}"
        workflow = AnimationWorkflow(
            self.ffmpeg,
            root / "reference.png",
            policy,
            self.images,
            ledger_path=root / "usage.sqlite3",
            repair_references={v.scene_id: v.path for v in prior},
        )
        command = request.model_copy(
            update={"workspace": str(workspace), "resume": workspace.exists()}
        )
        delivery = generate(command, workflow=workflow)
        atomic_write(saved, delivery.model_dump_json(indent=2))
        return delivery

    def _review(
        self,
        executor: SubscriptionExecutor,
        root: Path,
        standard: AnimationStandard,
        original: tuple[SceneImage, ...],
        painted: tuple[SceneImage, ...],
        round_number: int,
    ) -> tuple[StylizationReview, ...]:
        by_id = {v.scene_id: v for v in painted}
        groups = [(v,) for v in original] + [
            (original[i], original[i + 1]) for i in range(len(original) - 1)
        ]
        reviews = []
        for index, views in enumerate(groups):
            ids = tuple(v.scene_id for v in views)
            image_paths = (
                root / "reference.png",
                *(v.path for v in views),
                *(by_id[v.scene_id].path for v in views),
            )
            review = self._ask(
                executor,
                StylizationReview,
                root,
                f"review-{round_number}-{index}",
                AgentContext(
                    scene_ids=ids,
                    profile_id=standard.profile_id,
                    criteria=standard.criteria,
                    image_roles=(
                        "approved standard",
                        *(f"original {v.scene_id}" for v in views),
                        *(f"candidate {v.scene_id}" for v in views),
                    ),
                    round_number=round_number,
                ),
                image_paths,
                "Judge the candidate images directly against the actual approved "
                "animation reference and originals. "
                "Report observable evidence and concrete corrections, not keyword scores. "
                "Only severe visible blur/loss of readable structure, major "
                "departure from the approved animation medium, "
                "changed object identity/architecture or conflicting shared "
                "distant structures is critical. "
                "Small taste differences are minor and must not trigger a repaint."
                " Account for viewpoint perspective, "
                "occlusion and normal equirectangular distortion; do not treat them as conflicts. "
                "For paired views check only features visibly shared in the "
                "originals. Do not invent hidden facts. "
                "These are panorama textures, not rendered 3D walking evidence. An"
                " uncertain comparison is not proof of failure. "
                "Return the exact provided scene IDs and an empty issues list if "
                "there is no supported issue.",
            )
            if set(review.scene_ids) != set(ids) or len(review.scene_ids) != len(ids):
                raise ValueError("Reviewer changed its scene coverage")
            if any(
                not issue.scene_ids or not set(issue.scene_ids).issubset(ids)
                for issue in review.issues
            ):
                raise ValueError("Reviewer reported an unknown scene")
            reviews.append(review)
        return tuple(reviews)

    @staticmethod
    def _ask(
        executor: SubscriptionExecutor,
        output_type: type[T],
        root: Path,
        stage: str,
        context: AgentContext,
        images: tuple[Path, ...],
        instructions: str,
    ) -> T:
        for path in images:
            EnvironmentStylizationAgent._check_image(path)
        request = ExecutionInput(
            project_id=executor.grant.project_id,
            grant_ref=executor.grant.grant_ref,
            model_id=executor.grant.model_id,
            kind="environment_generation",
            prompt_version="stylization-agent-v1",
            policy_version="approved-point2-v2",
            instructions=instructions,
            payload_json=context.model_dump_json(),
            output_schema_json=json.dumps(output_type.model_json_schema()),
            image_paths=tuple(str(p.resolve()) for p in images),
            image_hashes=tuple(digest(p) for p in images),
        )
        frozen = root / f"{stage}-input.json"
        if frozen.is_file() and ExecutionInput.model_validate_json(frozen.read_bytes()) != request:
            raise ExecutionDenied("Saved agent stage changed; not redispatched")
        if not frozen.exists():
            atomic_write(frozen, request.model_dump_json(indent=2))
        response = executor.execute(request)
        value = output_type.model_validate_json(response.payload_json)
        atomic_write(root / f"{stage}.json", value.model_dump_json(indent=2))
        return value

    @staticmethod
    def _check_image(path: Path) -> None:
        if not path.is_file() or path.stat().st_size > 4 * 1024**2:
            raise ValueError("Agent reference/source image is missing or exceeds 4 MiB")
        with Image.open(path) as image:
            if image.width * image.height > 32_000_000:
                raise ValueError("Agent image exceeds supported pixel bounds")
            image.verify()

    @staticmethod
    def _images_from_html(path: Path, target: Path) -> tuple[SceneImage, ...]:
        if path.stat().st_size > 200 * 1024**2:
            raise ValueError("Tour HTML exceeds the image-evidence bound")
        match = re.search(SLOT, path.read_text(), re.S)
        if match is None:
            raise ValueError("Tour payload is missing")
        tour = record(json.loads(match[2]))
        if tour.get("schemaVersion") != 4:
            raise ValueError("Agent requires the supported native tour contract")
        target.mkdir(parents=True, exist_ok=True)
        images = []
        scenes = sequence(tour["scenes"])
        if not 1 <= len(scenes) <= 6:
            raise ValueError("Agent evidence supports 1 to 6 viewpoints")
        for index, value in enumerate(scenes):
            scene = record(value)
            raw = base64.b64decode(
                string(record(scene["panorama"])["data"]).split(",", 1)[1], validate=True
            )
            if len(raw) > 4 * 1024**2:
                raise ValueError("Panorama exceeds agent image evidence bound")
            with Image.open(io.BytesIO(raw)) as image:
                if image.width != image.height * 2 or image.width > 4096:
                    raise ValueError("Agent requires supported native 2:1 panorama evidence")
                image.verify()
            output = target / f"view-{index}.jpg"
            if output.exists() and output.read_bytes() != raw:
                raise ValueError("Saved evidence changed")
            if not output.exists():
                output.write_bytes(raw)
            images.append(SceneImage(string(scene["id"]), output))
        if len({v.scene_id for v in images}) != len(images):
            raise ValueError("Duplicate viewpoint identities")
        return tuple(images)

    @staticmethod
    def _original_images(request: AutomaticStyleRun, target: Path) -> tuple[SceneImage, ...]:
        source = Path(request.source.source)
        if request.source.kind == "panorama":
            return EnvironmentStylizationAgent._images_from_html(
                source / "vr_trial/index.html", target
            )
        if digest(source) != request.source.source_sha256:
            raise ValueError("Source archive changed")
        target.mkdir(exist_ok=True)
        images = []
        with zipfile.ZipFile(source) as outer:
            manifest = outer.getinfo("tour.json")
            if manifest.file_size > 2 * 1024**2:
                raise ValueError("Oversized tour metadata")
            tour = TourManifest.model_validate_json(outer.read(manifest))
            if not 1 <= len(tour.views) <= 6:
                raise ValueError("Agent supports 1 to 6 native tour viewpoints")
            for index, view in enumerate(tour.views):
                with outer.open(view.package) as nested, zipfile.ZipFile(nested) as bundle:
                    metadata = bundle.getinfo("scene/attachment.json")
                    if metadata.file_size > 2 * 1024**2:
                        raise ValueError("Oversized attachment")
                    attachment = record(json.loads(bundle.read(metadata)))
                    if attachment["source_scene_id"] != view.source_scene_id:
                        raise ValueError("Viewpoint evidence binding changed")
                    name = string(attachment["source_panorama"])
                    if name not in ("source-panorama.jpg", "source-panorama.png"):
                        raise ValueError("Unexpected original panorama path")
                    entry = bundle.getinfo("scene/" + name)
                    if entry.file_size > 4 * 1024**2:
                        raise ValueError("Original panorama exceeds evidence bound")
                    raw = bundle.read(entry)
                    with Image.open(io.BytesIO(raw)) as image:
                        if image.width != image.height * 2 or image.width > 4096:
                            raise ValueError("Unsupported original panorama evidence dimensions")
                        image.verify()
                    output = target / f"view-{index}.jpg"
                    if output.exists() and output.read_bytes() != raw:
                        raise ValueError("Frozen original evidence changed")
                    if not output.exists():
                        output.write_bytes(raw)
                    images.append(SceneImage(view.source_scene_id, output))
        return tuple(images)

    @staticmethod
    def _painted_images(
        delivery: AutomaticStyleDelivery, workspace: Path, target: Path, ids: tuple[str, ...]
    ) -> tuple[SceneImage, ...]:
        environment = (
            Path(delivery.environment)
            if delivery.environment
            else workspace / "animation/environment"
        )
        images = EnvironmentStylizationAgent._images_from_html(
            environment / "vr_trial/index.html", target
        )
        if tuple(v.scene_id for v in images) != ids:
            raise ValueError("Generated evidence does not preserve source viewpoints")
        return images
