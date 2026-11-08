"""Photo target to historical source assignment and scoped evidence preparation."""

from __future__ import annotations

import hashlib
import io
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageOps

from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.codex_semantics import CodexSemanticGateway, EvidenceImageBinding
from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.application.bootstrap import atomic_write
from pastport_evidence.application.evidence import CorpusIndex, EvidenceService
from pastport_evidence.domain.build import (
    MappingInventory,
    CandidateTextPage, CandidatePagePlan, CandidatePageRequest,
    ObjectReferenceSheet,
    PDFMatchPage,
    PDFMatchRequest,
    PDFObjectMatch,
)
from pastport_evidence.domain.evidence import (
    EvidenceScope,
    EvidenceSelection,
    HistoricalDescription,
    HistoricalSubject,
    SourceImageObservation,
)
from pastport_evidence.domain.execution import SubscriptionGrant
from pastport_evidence.domain.mapping import MappedObject, SourceEvidence
from pastport_evidence.domain.models import DomainModel, ProjectAssetRef
from pastport_evidence.domain.pdf import PDFExtractionStatus, PDFRegion, RegisteredPDF
from pastport_evidence.domain.photos import PhotoInventory
from pastport_evidence.domain.recognition import RecognitionResult, SceneEntity
from pastport_evidence.workflow.graph import (
    StageCommand,
    StageOutput,
)


class DocumentDraft(DomainModel):
    objects: tuple[MappedObject, ...]
    gaps: tuple[str, ...]


class _ActionStage:
    def __init__(self, action: Callable[[], StageOutput]) -> None:
        self._action = action

    def execute(self, command: StageCommand) -> StageOutput:
        print(json.dumps({"event": "stage_started", "stage": command.stage}), flush=True)
        output = self._action()
        print(
            json.dumps(
                {"event": "stage_completed", "stage": command.stage, "gap_count": len(output.gaps)}
            ),
            flush=True,
        )
        return output


@dataclass(frozen=True, slots=True)
class MappingPreparation:
    workspace: Path
    artifacts: Path
    grant: SubscriptionGrant
    mode: Literal["same_site", "demo_substitution"]
    binding: str
    assets: LocalAssetStore
    executor: SubscriptionExecutor
    mapping_prompt_version: str = field(default="v2", kw_only=True)
    evidence_prompt_version: str = field(default="v2", kw_only=True)

    indexed_retrieval: bool = field(default=False, kw_only=True)

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
        if self.mapping_prompt_version not in ("v2", "v3", "text-v1"):
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
                    (x, y) = (index % 5 * 300, index // 5 * 300)
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
        (document, recognition) = (self._pdf(), self._recognized())
        corpus = CorpusIndex(document)
        pages: list[PDFMatchPage] = []
        gaps: list[str] = []
        selected_pages = document.pages
        if self.indexed_retrieval and recognition.entities:
            plan_file = self.artifacts / "candidate-pages.json"
            if plan_file.exists():
                plan = CandidatePagePlan.model_validate_json(plan_file.read_bytes())
            else:
                plan = CodexSemanticGateway(self.executor, self.assets).candidate_pages(
                    CandidatePageRequest(objects=recognition.entities, source_sha256=document.source.asset.sha256,
                        pages=tuple(CandidateTextPage(page_index=p.page_index, text=p.original_text[:2400]) for p in document.pages)), self.grant)
                self._write("candidate-pages.json", plan)
            valid = {p.page_index for p in document.pages}
            if not plan.page_indices or not set(plan.page_indices) <= valid:
                raise ValueError("No valid candidate source pages; retrieval must be reviewed")
            selected_pages = tuple(p for p in document.pages if p.page_index in plan.page_indices)
            gaps.extend(plan.gaps)
            gaps.append("candidate_page_scope:not_exhaustive_source_scan")
        for page in selected_pages:
            passages = tuple(p for p in corpus.passages if p.page_index == page.page_index)
            if len(passages) > 10:
                gaps.append(f"pdf_mapping_text_truncated:page:{page.page_index + 1}")
            # Only old saved runs may reuse their already-rendered evidence images.
            image_ref = page.rendered_page if self.mapping_prompt_version != "text-v1" else None
            width, height = round(page.page_width), round(page.page_height)
            if image_ref is not None:
                with Image.open(self.assets.resolve_path(image_ref)) as saved:
                    width, height = saved.size
            elif self.mapping_prompt_version != "text-v1":
                raise ValueError("Saved visual-PDF policy lacks cached images; start a new text-first job")
            pages.append(
                PDFMatchPage(
                    page_index=page.page_index,
                    image=image_ref,
                    width=width,
                    height=height,
                    passages=passages,
                )
            )
            if page.extraction_status == PDFExtractionStatus.OCR_NEEDED:
                gaps.append(f"ocr_needed:page:{page.page_index + 1}")
        matches: list[PDFObjectMatch] = []
        receipts: list[str] = []
        subjects: dict[str, HistoricalSubject] = {}
        gateway = CodexSemanticGateway(self.executor, self.assets)
        if not recognition.entities:
            gaps.append("no_recognized_scene_objects")
        else:
            # Text-only pages do not consume the visual request's image slots.
            page_batch_size = 12 if self.mapping_prompt_version == "text-v1" else 3
            for start in range(0, len(pages), page_batch_size):
                if self.executor.remaining_calls() < 1:
                    gaps.append(f"pdf_mapping_budget_exhausted:from_page:{start + 1}")
                    break
                batch = tuple(
                    page.model_copy(update={"passages": page.passages[:10]})
                    for page in pages[start : start + page_batch_size]
                )
                for offset in range(0, len(recognition.entities), 100):
                    if self.executor.remaining_calls() < 1:
                        gaps.append("pdf_mapping_object_batch_budget_exhausted")
                        break
                    (result, receipt) = gateway.match_pdf(
                        PDFMatchRequest(
                            mode=self.mode,
                            prompt_version=self.mapping_prompt_version,
                            policy_version="narrative-proxy-v1"
                            if self.mapping_prompt_version in ("v2", "v3", "text-v1")
                            else "pdf-object-mapping-v1",
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
        resolved_matches = []
        for candidate in matches:
            parent = candidate.subject.parent_subject_id
            if parent is not None and parent not in subjects:
                gaps.append(f"unregistered_historical_parent:{candidate.subject.subject_id}")
                candidate = candidate.model_copy(
                    update={
                        "subject": candidate.subject.model_copy(update={"parent_subject_id": None})
                    }
                )
            resolved_matches.append(candidate)
        inventory = MappingInventory(
            matches=tuple(resolved_matches),
            pages=tuple(pages),
            receipt_refs=tuple(receipts),
            gaps=tuple(gaps),
        )
        self._write("mapping.json", inventory)
        return StageOutput(references=("artifact:mapping",), gaps=inventory.gaps)

    def evidence(self) -> StageOutput:
        if (self.artifacts / "review-draft.json").exists():
            cached_draft = DocumentDraft.model_validate_json(
                (self.artifacts / "review-draft.json").read_bytes()
            )
            return StageOutput(references=("artifact:review-draft",), gaps=cached_draft.gaps)
        (document, recognized) = (self._pdf(), self._recognized())
        inventory = MappingInventory.model_validate_json(
            (self.artifacts / "mapping.json").read_bytes()
        )
        corpus = CorpusIndex(document)
        by_object: dict[str, list[PDFObjectMatch]] = defaultdict(list)
        for item in inventory.matches:
            by_object[item.object_id].append(item)
        selected: dict[str, PDFObjectMatch] = {}
        gaps = [*recognized.gaps, *inventory.gaps]
        ranks = {"same_object": 0, "same_kind": 1, "functional_analogy": 2, "substitution": 3}
        for object_id, candidates in by_object.items():
            pool = candidates
            if self.mapping_prompt_version in ("v2", "v3", "text-v1"):
                documented = [c for c in candidates if c.story_support == "documented_activity"]
                pool = documented or candidates
            rank = min(ranks[c.relationship] for c in pool)
            best = [c for c in pool if ranks[c.relationship] == rank]
            if len({c.subject.subject_id for c in best}) != 1:
                gaps.append(f"ambiguous_historical_assignment:{object_id}")
                continue
            best.sort(key=lambda c: (c.story_support != "documented_activity", c.page_index))
            selected[object_id] = best[0]
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
                objects.append(MappedObject(entity=entity))
                gaps.append(f"no_historical_match:{entity.object_id}")
                continue
            selected_page = next(p for p in inventory.pages if p.page_index == candidate.page_index)
            source_page = document.pages[candidate.page_index]
            crop_ref: ProjectAssetRef | None = None
            observation: SourceImageObservation | None = None
            bindings: tuple[EvidenceImageBinding, ...] = ()
            if candidate.region and selected_page.image is not None:
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
                    depiction="page_context"
                    if candidate.source_image_role != "object_image"
                    else "component",
                    depicted_subject_id=candidate.subject.subject_id,
                )
                bindings = (EvidenceImageBinding(image_id=image_id, image=crop_ref),)
            passage_by_id = {p.passage_id: p for p in corpus.passages}
            found = {
                p.passage_id: p
                for p in corpus.select(candidate.subject, observation, max_passages=30)
            }
            preferred = {
                p.passage_id: p for p in corpus.passages if p.page_index == candidate.page_index
            }
            for passage_id in candidate.passage_ids:
                preferred[passage_id] = passage_by_id[passage_id]
            preferred.update(found)
            found = preferred
            selection = EvidenceSelection(
                subject=candidate.subject,
                passages=tuple(found.values())[:40],
                image=observation,
                grant_ref=self.grant.grant_ref,
                model_id=self.grant.model_id,
                prompt_version=self.evidence_prompt_version,
                policy_version="evidence-v1",
            )
            draft: HistoricalDescription | None = None
            evidence = None
            if self.indexed_retrieval:
                exact = tuple(passage_by_id[key] for key in candidate.passage_ids)
                for passage in exact:
                    corpus.validate_passage(passage)
                if exact:
                    draft = HistoricalDescription(subject_id=candidate.subject.subject_id,
                        version=1, introduction=exact[0].quote[:1200])
                else:
                    gaps.append(f"missing_exact_quote:{entity.object_id}")
                gaps.append(f"historical_association_pending_human_review:{entity.object_id}")
            elif self.executor.remaining_calls() > 0 and selection.passages:
                service = EvidenceService(
                    corpus, CodexSemanticGateway(self.executor, self.assets, bindings)
                )
                assessed = service.retrieve_and_associate(selection, allow_partial=True)
                (selection, evidence) = (assessed.selection, assessed.evidence)
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
                draft = HistoricalDescription(
                    subject_id=candidate.subject.subject_id,
                    version=1,
                    introduction="\n".join(introduction),
                    background="\n".join(background),
                )
            else:
                gaps.append(f"evidence_unavailable_or_budget_exhausted:{entity.object_id}")
            claims = evidence.claims if evidence else ()
            used = set(candidate.passage_ids) if self.indexed_retrieval else {key for claim in claims for key in claim.passage_ids}
            passages = tuple(p for p in selection.passages if p.passage_id in used)
            objects.append(
                MappedObject(
                    entity=entity,
                    historical_subject_id=candidate.subject.subject_id,
                    draft=draft,
                    evidence_refs=tuple(p.passage_id for p in passages),
                    source_evidence=SourceEvidence(
                        historical_subject_id=candidate.subject.subject_id,
                        title=candidate.subject.label,
                        pdf_page_number=candidate.page_index + 1,
                        printed_page=None,
                        original_quote="\n\n".join(p.quote for p in passages),
                        translation="",
                        scope="Exact source excerpt; historical association pending review" if self.indexed_retrieval else "See independently scoped claims",
                        limitation=candidate.basis,
                        source_page_sha256=hashlib.sha256(
                            source_page.original_text.encode()
                        ).hexdigest(),
                        quote_representation="raw_page",
                        source_ref=document.source,
                        passages=passages,
                        claims=claims,
                        image_association_state=(
                            "linked" if evidence and evidence.associations else "candidate"
                        ),
                        source_image_role=candidate.source_image_role,
                        source_image=crop_ref,
                        page_image=source_page.rendered_page,
                        background=draft.background if draft else "",
                    ),
                )
            )
        draft_result = DocumentDraft(objects=tuple(objects), gaps=tuple(dict.fromkeys(gaps)))
        self._write("review-draft.json", draft_result)
        return StageOutput(references=("artifact:review-draft",), gaps=draft_result.gaps)
