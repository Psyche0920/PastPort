"""PDF + supported tour export to numbered VR and an editable local workbench."""

from __future__ import annotations

import hashlib
import io
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageOps

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.codex_semantics import CodexSemanticGateway, EvidenceImageBinding
from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.adapters.execution import SubscriptionExecutor
from pastport_pdf_vr.adapters.identity import SQLiteSceneRepository
from pastport_pdf_vr.adapters.projection import PanoramaProjector
from pastport_pdf_vr.adapters.tour import TourImporter
from pastport_pdf_vr.application.bootstrap import ExportStage, atomic_write
from pastport_pdf_vr.application.evidence import CorpusIndex, EvidenceService
from pastport_pdf_vr.application.pdf_ingestion import PDFIngestionService
from pastport_pdf_vr.application.recognition import SceneRecognitionService
from pastport_pdf_vr.domain.build import (
    BuildSummary,
    MappingInventory,
    ObjectReferenceSheet,
    PDFMatchPage,
    PDFMatchRequest,
    PDFObjectMatch,
)
from pastport_pdf_vr.domain.editorial import PreviewAnchor, PreviewObject, ReplayEvidence
from pastport_pdf_vr.domain.evidence import (
    DisplayCopy,
    EvidenceScope,
    EvidenceSelection,
    HistoricalSubject,
    SourceImageObservation,
)
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.geometry import EquirectangularTransform, PerspectiveTransform
from pastport_pdf_vr.domain.models import DomainModel, ProcessingLimits, ProjectAssetRef
from pastport_pdf_vr.domain.pdf import PDFRegion, RegisteredPDF
from pastport_pdf_vr.domain.photos import PhotoInventory
from pastport_pdf_vr.domain.recognition import (
    MatchingImage,
    PanoramaView,
    RecognitionResult,
    SceneEntity,
)
from pastport_pdf_vr.domain.tour import ImportedTour
from pastport_pdf_vr.ports.execution import SemanticTransport
from pastport_pdf_vr.ports.pdf import PDFDocumentReader
from pastport_pdf_vr.ports.scene import PanoramaSourceReader
from pastport_pdf_vr.workflow.graph import (
    FixedStage,
    FixedWorkflow,
    StageCommand,
    StageJournal,
    StageOutput,
    StageRecovery,
)


class BuildDraft(DomainModel):
    objects: tuple[PreviewObject, ...]
    anchors: tuple[PreviewAnchor, ...]
    gaps: tuple[str, ...]


class _ActionStage:
    def __init__(self, action: Callable[[], StageOutput]) -> None:
        self._action = action

    def execute(self, command: StageCommand) -> StageOutput:
        return self._action()


@dataclass(frozen=True, slots=True)
class MappingPreparation:
    workspace: Path
    artifacts: Path
    grant: SubscriptionGrant
    mode: Literal["same_site", "demo_substitution"]
    binding: str
    assets: LocalAssetStore
    executor: SubscriptionExecutor
    mapping_prompt_version: str = field(default="v1", kw_only=True)
    evidence_prompt_version: str = field(default="v1", kw_only=True)

    def _write(self, name: str, value: DomainModel) -> None:
        atomic_write(self.artifacts / name, value.model_dump_json())

    def _pdf(self) -> RegisteredPDF:
        return RegisteredPDF.model_validate_json((self.artifacts / "pdf.json").read_bytes())

    def _recognized(self) -> RecognitionResult:
        return RecognitionResult.model_validate_json(
            (self.artifacts / "recognition.json").read_bytes()
        )

    def _photo_reference_sheets(
        self, entities: tuple[SceneEntity, ...]
    ) -> tuple[ObjectReferenceSheet, ...]:
        if self.mapping_prompt_version != "v2":
            return ()
        inventory = PhotoInventory.model_validate_json(
            (self.artifacts / "photo-inventory.json").read_bytes()
        )
        observations = sorted(inventory.observations, key=lambda o: o.identity_state != "confirmed")
        sheets: list[ObjectReferenceSheet] = []
        for offset in range(0, len(entities), 25):
            group = entities[offset : offset + 25]
            rows = (len(group) + 4) // 5
            with Image.new("RGB", (1500, rows * 300), "white") as sheet:
                draw = ImageDraw.Draw(sheet)
                for index, entity in enumerate(group):
                    x, y = index % 5 * 300, index // 5 * 300
                    observation = next(
                        (o for o in observations if o.object_id == entity.object_id), None
                    )
                    draw.text(
                        (x + 5, y + 5), str(entity.display_number), fill="black", font_size=24
                    )
                    if observation is not None:
                        with Image.open(self.assets.resolve_path(observation.crop)) as raw:
                            with ImageOps.contain(raw, (290, 250)) as tile:
                                sheet.paste(tile, (x + 5, y + 40))
                stream = io.BytesIO()
                sheet.save(stream, "JPEG", quality=90)
            reference = self.assets.register_bytes(
                self.grant.project_id, stream.getvalue(), "image/jpeg", 4 * 1024 * 1024
            ).reference
            sheets.append(
                ObjectReferenceSheet(
                    image=reference,
                    object_ids=tuple(e.object_id for e in group),
                    display_numbers=tuple(e.display_number for e in group),
                    columns=5,
                    rows=rows,
                )
            )
        return tuple(sheets)

    def map_pdf(self) -> StageOutput:
        target = self.artifacts / "mapping.json"
        if target.exists():
            inventory = MappingInventory.model_validate_json(target.read_bytes())
            return StageOutput(references=("artifact:mapping",), gaps=inventory.gaps)
        document, recognition = self._pdf(), self._recognized()
        corpus = CorpusIndex(document)
        pages: list[PDFMatchPage] = []
        gaps: list[str] = []
        for page in document.pages:
            with Image.open(self.assets.resolve_path(page.rendered_page)) as raw:
                image = raw.convert("RGB")
                image.thumbnail((1536, 1536))
                encoded = io.BytesIO()
                image.save(encoded, format="JPEG", quality=85)
                width, height = image.size
                image.close()
            reference = self.assets.register_bytes(
                self.grant.project_id, encoded.getvalue(), "image/jpeg", 4 * 1024 * 1024
            )
            passages = tuple(p for p in corpus.passages if p.page_index == page.page_index)
            if len(passages) > 10:
                gaps.append(f"pdf_mapping_text_truncated:page:{page.page_index + 1}")
            pages.append(
                PDFMatchPage(
                    page_index=page.page_index,
                    image=reference.reference,
                    width=width,
                    height=height,
                    passages=passages,
                )
            )
            if not page.original_text.strip():
                gaps.append(f"ocr_needed:page:{page.page_index + 1}")
        matches: list[PDFObjectMatch] = []
        receipts: list[str] = []
        subjects: dict[str, HistoricalSubject] = {}
        gateway = CodexSemanticGateway(self.executor, self.assets)
        if not recognition.entities:
            gaps.append("no_recognized_scene_objects")
        else:
            for start in range(0, len(pages), 3):
                if self.executor.remaining_calls() < 1:
                    gaps.append(f"pdf_mapping_budget_exhausted:from_page:{start + 1}")
                    break
                # Bound both image batches and selected native-text context.
                batch = tuple(
                    page.model_copy(update={"passages": page.passages[:10]})
                    for page in pages[start : start + 3]
                )
                for offset in range(0, len(recognition.entities), 100):
                    if self.executor.remaining_calls() < 1:
                        gaps.append("pdf_mapping_object_batch_budget_exhausted")
                        break
                    result, receipt = gateway.match_pdf(
                        PDFMatchRequest(
                            mode=self.mode,
                            prompt_version=self.mapping_prompt_version,
                            policy_version=(
                                "narrative-proxy-v1"
                                if self.mapping_prompt_version == "v2"
                                else "pdf-object-mapping-v1"
                            ),
                            objects=recognition.entities[offset : offset + 100],
                            reference_sheets=self._photo_reference_sheets(
                                recognition.entities[offset : offset + 100]
                            ),
                            known_subjects=tuple(subjects.values()),
                            pages=batch,
                            grant=self.grant,
                        )
                    )
                    receipts.append(receipt)
                    for candidate in result.matches:

                        def canonical(key: str) -> str:
                            if key in subjects:
                                return key
                            return (
                                "historical:"
                                + hashlib.sha256(
                                    (document.source.asset.sha256 + key).encode()
                                ).hexdigest()[:32]
                            )

                        subject = candidate.subject.model_copy(
                            update={
                                "subject_id": canonical(candidate.subject.subject_id),
                                "parent_subject_id": canonical(candidate.subject.parent_subject_id)
                                if candidate.subject.parent_subject_id
                                else None,
                            }
                        )
                        subjects.setdefault(subject.subject_id, subject)
                        matches.append(candidate.model_copy(update={"subject": subject}))
                    gaps.extend(result.gaps)
        inventory = MappingInventory(
            matches=tuple(matches),
            pages=tuple(pages),
            receipt_refs=tuple(receipts),
            gaps=tuple(gaps),
        )
        self._write("mapping.json", inventory)
        return StageOutput(references=("artifact:mapping",), gaps=inventory.gaps)

    def evidence(self) -> StageOutput:
        if (self.artifacts / "review-draft.json").exists():
            cached_draft = BuildDraft.model_validate_json(
                (self.artifacts / "review-draft.json").read_bytes()
            )
            return StageOutput(references=("artifact:review-draft",), gaps=cached_draft.gaps)
        document, recognized = self._pdf(), self._recognized()
        inventory = MappingInventory.model_validate_json(
            (self.artifacts / "mapping.json").read_bytes()
        )
        corpus = CorpusIndex(document)
        by_object: dict[str, list[PDFObjectMatch]] = defaultdict(list)
        for item in inventory.matches:
            by_object[item.object_id].append(item)
        selected: dict[str, PDFObjectMatch] = {}
        gaps = [*recognized.gaps, *inventory.gaps]
        for row in recognized.dispositions:
            if row.position is None:
                gaps.append(f"unlocated:{row.object_id}:{row.view_id}:{row.state}")
        ranks = {"same_object": 0, "same_kind": 1, "functional_analogy": 2, "substitution": 3}
        for object_id, candidates in by_object.items():
            pool = candidates
            if self.mapping_prompt_version == "v2":
                documented = [c for c in candidates if c.story_support == "documented_activity"]
                pool = documented or candidates
            rank = min(ranks[c.relationship] for c in pool)
            best = [c for c in pool if ranks[c.relationship] == rank]
            if len({c.subject.subject_id for c in best}) != 1:
                gaps.append(f"ambiguous_historical_assignment:{object_id}")
                continue
            best.sort(key=lambda c: (c.story_support != "documented_activity", c.page_index))
            selected[object_id] = best[0]
        # Different physical scene objects must not silently collapse to one historical object.
        assigned: dict[str, list[str]] = defaultdict(list)
        for object_id, chosen in selected.items():
            assigned[chosen.subject.subject_id].append(object_id)
        for subject, ids in assigned.items():
            if len(ids) > 1:
                gaps.append(f"historical_identity_collision:{subject}")
                for object_id in ids:
                    selected.pop(object_id, None)
        objects = []
        for entity in recognized.entities:
            candidate = selected.get(entity.object_id)
            if candidate is None:
                objects.append(PreviewObject(entity=entity))
                gaps.append(f"no_historical_match:{entity.object_id}")
                continue
            selected_page = next(p for p in inventory.pages if p.page_index == candidate.page_index)
            source_page = document.pages[candidate.page_index]
            crop_ref: ProjectAssetRef | None = None
            observation: SourceImageObservation | None = None
            bindings: tuple[EvidenceImageBinding, ...] = ()
            if candidate.region:
                region = candidate.region
                with Image.open(self.assets.resolve_path(selected_page.image)) as raw:
                    with raw.crop(
                        (
                            int(region.top_left.x),
                            int(region.top_left.y),
                            int(region.bottom_right.x + 0.999),
                            int(region.bottom_right.y + 0.999),
                        )
                    ) as crop:
                        encoded = io.BytesIO()
                        with crop.convert("RGB") as rgb:
                            rgb.save(encoded, format="JPEG", quality=88)
                crop_ref = self.assets.register_bytes(
                    self.grant.project_id, encoded.getvalue(), "image/jpeg", 4 * 1024 * 1024
                ).reference
                image_id = (
                    "pdf-crop:"
                    + hashlib.sha256(
                        (entity.object_id + candidate.model_dump_json()).encode()
                    ).hexdigest()[:32]
                )
                observation = SourceImageObservation(
                    image_id=image_id,
                    source=document.source,
                    page_index=candidate.page_index,
                    region=PDFRegion(
                        x0=region.top_left.x / selected_page.width * source_page.page_width,
                        top=region.top_left.y / selected_page.height * source_page.page_height,
                        x1=region.bottom_right.x / selected_page.width * source_page.page_width,
                        bottom=region.bottom_right.y
                        / selected_page.height
                        * source_page.page_height,
                    ),
                    description=candidate.basis,
                    depicted_subject_id=candidate.subject.subject_id,
                )
                bindings = (EvidenceImageBinding(image_id=image_id, image=crop_ref),)
            passage_by_id = {p.passage_id: p for p in corpus.passages}
            found = {
                p.passage_id: p
                for p in corpus.select(candidate.subject, observation, max_passages=30)
            }
            for passage_id in candidate.passage_ids:
                found[passage_id] = passage_by_id[passage_id]
            selection = EvidenceSelection(
                subject=candidate.subject,
                passages=tuple(found.values())[:40],
                image=observation,
                grant_ref=self.grant.grant_ref,
                model_id=self.grant.model_id,
                prompt_version=self.evidence_prompt_version,
                policy_version="evidence-v1",
            )
            draft: DisplayCopy | None = None
            evidence = None
            if self.executor.remaining_calls() > 0 and selection.passages:
                service = EvidenceService(
                    corpus, CodexSemanticGateway(self.executor, self.assets, bindings)
                )
                assessed = service.retrieve_and_associate(selection, allow_partial=True)
                selection, evidence = assessed.selection, assessed.evidence
                gaps.extend(
                    f"evidence_validation:{entity.object_id}:{gap}"
                    for gap in assessed.validation_gaps
                )
                if assessed.retrieval_gap:
                    gaps.append(f"evidence_retrieval_gap:{entity.object_id}")
                introduction: list[str] = []
                background: list[str] = []
                for claim in evidence.claims:
                    target = introduction if claim.scope is EvidenceScope.DIRECT else background
                    limit = 1200 if target is introduction else 6000
                    count = 4 if target is introduction else 8
                    if (
                        len(target) < count
                        and sum(len(text) for text in target) + len(claim.statement) <= limit
                    ):
                        target.append(claim.statement)
                draft = DisplayCopy(
                    subject_id=candidate.subject.subject_id,
                    version=1,
                    introduction="\n".join(introduction),
                    background="\n".join(background),
                )
            else:
                gaps.append(f"evidence_unavailable_or_budget_exhausted:{entity.object_id}")
            claims = evidence.claims if evidence else ()
            used = {key for claim in claims for key in claim.passage_ids}
            passages = tuple(p for p in selection.passages if p.passage_id in used)
            objects.append(
                PreviewObject(
                    entity=entity,
                    historical_subject_id=candidate.subject.subject_id,
                    draft=draft,
                    evidence_refs=tuple(p.passage_id for p in passages),
                    replay_evidence=ReplayEvidence(
                        historical_subject_id=candidate.subject.subject_id,
                        title=candidate.subject.label,
                        pdf_page_number=candidate.page_index + 1,
                        printed_page=None,
                        original_quote="\n\n".join(p.quote for p in passages),
                        translation="",
                        scope="See independently scoped claims",
                        limitation=candidate.basis,
                        source_page_sha256=hashlib.sha256(
                            source_page.original_text.encode()
                        ).hexdigest(),
                        quote_representation="raw_page",
                        source_ref=document.source,
                        passages=passages,
                        claims=claims,
                        source_image=crop_ref,
                        page_image=source_page.rendered_page,
                        background=draft.background if draft else "",
                    ),
                )
            )
        anchors = tuple(
            PreviewAnchor(
                object_id=row.object_id,
                view_id=row.view_id,
                panorama=row.panorama,
                panorama_revision=row.panorama_revision,
                position=row.position,
            )
            for row in recognized.dispositions
            if row.position is not None
        )
        draft_result = BuildDraft(
            objects=tuple(objects), anchors=anchors, gaps=tuple(dict.fromkeys(gaps))
        )
        self._write("review-draft.json", draft_result)
        return StageOutput(references=("artifact:review-draft",), gaps=draft_result.gaps)


@dataclass(frozen=True, slots=True)
class _BuildContext(MappingPreparation):
    pdf_path: Path
    tour_path: Path
    limits: ProcessingLimits
    expected_pdf_sha: str
    expected_tour: ImportedTour
    reader: PDFDocumentReader

    def _tour(self) -> ImportedTour:
        return ImportedTour.model_validate_json((self.artifacts / "tour.json").read_bytes())

    def ingest(self) -> StageOutput:
        existing = self.workspace / "tour.json"
        if existing.exists():
            current = ImportedTour.model_validate_json(existing.read_bytes())
            if current.source.project_id != self.grant.project_id:
                raise ValueError("Use a separate workspace for each project")
            snapshot = SQLiteEditorialRepository(self.workspace / "editorial.sqlite3").snapshot(
                self.grant.project_id
            )
            if snapshot.mode == "synthetic_replay":
                raise ValueError(
                    "Use a new build workspace; never replace a legacy replay in place"
                )
        if (self.artifacts / "pdf.json").exists() and (self.artifacts / "tour.json").exists():
            document, tour = self._pdf(), self._tour()
            self.assets.resolve_path(document.source)
            self.assets.resolve_path(tour.source)
        else:
            tour = TourImporter(self.assets).import_html(
                self.grant.project_id, self.tour_path, self.limits
            )
            document = PDFIngestionService(self.assets, self.reader).register_and_extract(
                self.grant.project_id, self.pdf_path, self.limits
            )
            if document.source.asset.sha256 != self.expected_pdf_sha or tour != self.expected_tour:
                raise ValueError("Build inputs changed after immutable binding")
            self._write("tour.json", tour)
            self._write("pdf.json", document)
        return StageOutput(
            references=(tour.source.asset.resource_id, document.source.asset.resource_id)
        )

    def recognize(self) -> StageOutput:
        if (self.artifacts / "recognition.json").exists():
            result = self._recognized()
            return StageOutput(references=("artifact:recognition",), gaps=result.gaps)
        views: list[PanoramaView] = []
        projector = PanoramaProjector()
        for view in self._tour().views:
            source = self.assets.resolve_path(view.panorama)
            transforms = [
                EquirectangularTransform(
                    source_width=view.width,
                    source_height=view.height,
                    image_width=2048,
                    image_height=1024,
                )
            ]
            images: list[MatchingImage] = []
            overview = transforms[0]
            rendered = self.assets.register_bytes(
                self.grant.project_id,
                projector.render(source, overview),
                "image/jpeg",
                4 * 1024 * 1024,
            )
            images.append(
                MatchingImage(
                    image_id=f"overview:{view.view_id}",
                    view_id=view.view_id,
                    image=rendered.reference,
                    panorama=view.panorama,
                    panorama_revision=view.revision,
                    transform=overview,
                    inspection_level="overview",
                )
            )
            poses = [(yaw, 0.0) for yaw in (-150.0, -90.0, -30.0, 30.0, 90.0, 150.0)]
            poses.extend(((0.0, 60.0), (0.0, -60.0)))
            for number, (yaw, pitch) in enumerate(poses):
                transform = PerspectiveTransform(
                    source_width=view.width,
                    source_height=view.height,
                    image_width=1024,
                    image_height=1024,
                    center_yaw=yaw,
                    center_pitch=pitch,
                    horizontal_fov=100.0,
                )
                image = self.assets.register_bytes(
                    self.grant.project_id,
                    projector.render(source, transform),
                    "image/jpeg",
                    4 * 1024 * 1024,
                )
                images.append(
                    MatchingImage(
                        image_id=f"detail:{view.view_id}:{number}",
                        view_id=view.view_id,
                        image=image.reference,
                        panorama=view.panorama,
                        panorama_revision=view.revision,
                        transform=transform,
                        inspection_level="detail",
                    )
                )
            views.append(
                PanoramaView(
                    view_id=view.view_id,
                    panorama=view.panorama,
                    panorama_revision=view.revision,
                    images=tuple(images),
                )
            )
        remaining = self.executor.remaining_calls()
        if remaining < 1:
            result = RecognitionResult(
                entities=(), dispositions=(), calls_used=0, gaps=("recognition_budget_exhausted",)
            )
        else:
            result = SceneRecognitionService(
                SQLiteSceneRepository(self.workspace / "identities.sqlite3"),
                CodexSemanticGateway(self.executor, self.assets),
            ).run(
                self.grant.project_id,
                self.binding,
                tuple(views),
                self.grant.grant_ref,
                "v1",
                "matching-v1",
                min(remaining, max(1, len(views) * 2)),
                model_id=self.grant.model_id,
            )
        self._write("recognition.json", result)
        return StageOutput(references=("artifact:recognition",), gaps=result.gaps)

    def publish(self) -> StageOutput:
        draft = BuildDraft.model_validate_json((self.artifacts / "review-draft.json").read_bytes())
        repository = SQLiteEditorialRepository(self.workspace / "editorial.sqlite3")
        repository.publish_proposals(
            self.grant.project_id, self.binding, "model_generated", draft.objects, draft.anchors
        )
        atomic_write(self.workspace / "tour.json", self._tour().model_dump_json())
        summary = BuildSummary(
            project_id=self.grant.project_id,
            input_binding=self.binding,
            mapping_mode=self.mode,
            object_count=len(draft.objects),
            anchor_count=len(draft.anchors),
            gaps=draft.gaps,
            status="completed_with_gaps" if draft.gaps else "completed",
        )
        atomic_write(self.workspace / "build-summary.json", summary.model_dump_json())
        return StageOutput(references=("preview:" + self.grant.project_id,), gaps=draft.gaps)


class AutomaticBuildWorkflow:
    def __init__(self, reader: PDFDocumentReader, transport: SemanticTransport) -> None:
        self._reader, self._transport = reader, transport

    def run(
        self,
        pdf_path: Path,
        tour_path: Path,
        workspace: Path,
        grant: SubscriptionGrant,
        run_id: str,
        mode: Literal["same_site", "demo_substitution"] = "same_site",
        large_pdf: bool = False,
        resume_evidence: bool = False,
    ) -> tuple[StageOutput, ...]:
        limits = ProcessingLimits(
            max_model_calls=grant.max_calls,
            budget_usd=Decimal("0.01"),
            pdf_max_bytes=(512 if large_pdf else 64) * 1024 * 1024,
        )
        if not pdf_path.is_file() or pdf_path.stat().st_size > limits.pdf_max_bytes:
            raise ValueError(
                "PDF missing or exceeds input profile; use --large-pdf explicitly if needed"
            )
        if not tour_path.is_file() or tour_path.stat().st_size > limits.tour_max_expanded_bytes:
            raise ValueError("Tour missing or oversized")
        digest = hashlib.sha256()
        file_hashes: list[str] = []
        for path in (pdf_path, tour_path):
            file_digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    file_digest.update(chunk)
            file_hashes.append(file_digest.hexdigest())
            digest.update(file_digest.digest())
        asset_store = LocalAssetStore(workspace / "assets")
        tour_reader: PanoramaSourceReader = TourImporter(asset_store)
        admitted_tour = tour_reader.import_html(grant.project_id, tour_path, limits)
        digest.update(admitted_tour.model_dump_json().encode())
        digest.update((grant.model_dump_json() + mode + str(large_pdf) + "automatic-v1").encode())
        binding = "build:" + digest.hexdigest()
        artifacts = workspace / "runs" / digest.hexdigest()
        artifacts.mkdir(parents=True, exist_ok=True)
        context = _BuildContext(
            workspace=workspace,
            artifacts=artifacts,
            pdf_path=pdf_path,
            tour_path=tour_path,
            grant=grant,
            limits=limits,
            mode=mode,
            binding=binding,
            expected_pdf_sha=file_hashes[0],
            expected_tour=admitted_tour,
            assets=LocalAssetStore(workspace / "assets"),
            executor=SubscriptionExecutor(
                workspace / "codex-executions.sqlite3", grant, self._transport
            ),
            reader=self._reader,
        )
        stages = tuple(
            FixedStage(name, _ActionStage(action))
            for name, action in (
                ("ingest", context.ingest),
                ("recognize", context.recognize),
                ("map_pdf", context.map_pdf),
                ("evidence", context.evidence),
                ("publish", context.publish),
            )
        ) + (FixedStage("export_snapshot", ExportStage(grant.project_id, workspace)),)
        recovery = None
        if resume_evidence:
            # Completed receipts are reusable; unknown dispatches must still be reconciled first.
            context.executor.remaining_calls()
            recovery = StageRecovery(
                stage="evidence",
                expected_error="EvidenceValidationError",
                reason="Operator-authorized partial-evidence validation after settled usage audit",
            )
        return FixedWorkflow(
            StageJournal(workspace / "stages.sqlite3"), stages, "automatic-v1"
        ).run(grant.project_id, run_id, binding, recovery=recovery)
