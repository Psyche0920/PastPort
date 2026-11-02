"""Bind existing semantic ports to one grant-scoped, metered Codex executor."""

import json
from typing import Literal, TypeVar

from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.adapters.structured_output import StrictOutputSchema
from pastport_evidence.application.photos import PhotoRecognitionService
from pastport_evidence.application.prompting import load_semantic_prompt
from pastport_evidence.domain.build import PDFMatchPayload, PDFMatchRequest, CandidatePagePlan, CandidatePageRequest
from pastport_evidence.domain.execution import SubscriptionGrant
from pastport_evidence.domain.evidence import (
    EvidencePayload,
    EvidenceProposal,
    EvidenceSelection,
)
from pastport_evidence.domain.execution import ExecutionDenied, ExecutionInput
from pastport_evidence.domain.models import DomainModel, ProjectAssetRef
from pastport_evidence.domain.photos import (
    CompactPhotoInspectionPayload,
    PhotoInspection,
    PhotoInspectionPayload,
    PhotoInspectionRequest,
)
from pastport_evidence.ports.assets import AssetStore

Payload = TypeVar("Payload", bound=DomainModel)


class EvidenceImageBinding(DomainModel):
    image_id: str
    image: ProjectAssetRef


class CodexSemanticGateway:
    def __init__(
        self,
        executor: SubscriptionExecutor,
        assets: AssetStore,
        evidence_images: tuple[EvidenceImageBinding, ...] = (),
        photo_prompt_version: Literal["v1", "v2", "v3"] = "v1",
    ) -> None:
        (self._executor, self._assets) = (executor, assets)
        self._photo_prompt_version = photo_prompt_version
        self._images = {item.image_id: item.image for item in evidence_images}
        if len(self._images) != len(evidence_images):
            raise ValueError("Source crop IDs must be unique")

    def _execute(
        self,
        kind: Literal[
            "evidence_association",
            "pdf_matching",
            "photo_inspection",
        ],
        request: DomainModel,
        output: type[Payload],
        images: tuple[ProjectAssetRef, ...],
        grant_ref: str,
        model_id: str,
        prompt_version: str,
        policy_version: str,
    ) -> tuple[Payload, str]:
        project = self._executor.grant.project_id
        if any(image.project_id != project for image in images):
            raise ExecutionDenied("Model image belongs to another project")
        result = self._executor.execute(
            ExecutionInput(
                project_id=project,
                grant_ref=grant_ref,
                model_id=model_id,
                kind=kind,
                prompt_version=prompt_version,
                policy_version=policy_version,
                instructions=load_semantic_prompt(kind, prompt_version),
                payload_json=request.model_dump_json(),
                output_schema_json=StrictOutputSchema.convert(
                    json.dumps(output.model_json_schema())
                ),
                image_paths=tuple(str(self._assets.resolve_path(image)) for image in images),
                image_hashes=tuple(image.asset.sha256 for image in images),
            )
        )
        return (output.model_validate_json(result.payload_json), result.receipt_ref)

    def inspect_photos(self, request: PhotoInspectionRequest) -> PhotoInspection:
        (payload, receipt) = self._execute(
            "photo_inspection",
            request,
            CompactPhotoInspectionPayload if self._photo_prompt_version in ("v2", "v3") else PhotoInspectionPayload,
            tuple(p.image for p in request.photos) + tuple(r.image for r in request.references),
            request.grant_ref,
            request.model_id,
            self._photo_prompt_version,
            "photo-identity-v1",
        )
        result = PhotoInspection.model_validate_json(
            json.dumps({**payload.model_dump(mode="json"), "receipt_ref": receipt})
        )
        PhotoRecognitionService.validate(request, result)
        return result

    def _source_images(self, request: EvidenceSelection) -> tuple[ProjectAssetRef, ...]:
        project = self._executor.grant.project_id
        if any(passage.source.project_id != project for passage in request.passages):
            raise ExecutionDenied("Evidence passage belongs to another project")
        if request.image is None:
            return ()
        image = self._images.get(request.image.image_id)
        if image is None or request.image.source.project_id != project:
            raise ExecutionDenied("PDF image needs an explicitly registered source crop")
        return (image,)

    def associate(self, request: EvidenceSelection) -> EvidenceProposal:
        (payload, receipt) = self._execute(
            "evidence_association",
            request,
            EvidencePayload,
            self._source_images(request),
            request.grant_ref,
            request.model_id,
            request.prompt_version,
            request.policy_version,
        )
        return EvidenceProposal(**payload.model_dump(), receipt_ref=receipt)

    def candidate_pages(self, request: CandidatePageRequest, grant: SubscriptionGrant) -> CandidatePagePlan:
        payload, _ = self._execute("pdf_matching", request, CandidatePagePlan, (),
            grant.grant_ref, grant.model_id, "index-v1", "candidate-index-v1")
        allowed = {page.page_index for page in request.pages}
        if len(set(payload.page_indices)) != len(payload.page_indices) or not set(payload.page_indices) <= allowed:
            raise ValueError("Candidate plan changed source page identity")
        return payload

    def match_pdf(self, request: PDFMatchRequest) -> tuple[PDFMatchPayload, str]:
        (payload, receipt) = self._execute(
            "pdf_matching",
            request,
            PDFMatchPayload,
            tuple(page.image for page in request.pages)
            + tuple(sheet.image for sheet in request.reference_sheets),
            request.grant.grant_ref,
            request.grant.model_id,
            request.prompt_version,
            request.policy_version,
        )
        objects = {item.object_id for item in request.objects}
        pages = {page.page_index: page for page in request.pages}
        passage_ids = {item.passage_id for page in request.pages for item in page.passages}
        for match in payload.matches:
            if match.object_id not in objects or match.page_index not in pages:
                raise ValueError("PDF mapping changed object/page identity")
            if not set(match.passage_ids) <= passage_ids:
                raise ValueError("PDF mapping cites an unprovided passage")
            if not match.region and (not match.passage_ids):
                raise ValueError("PDF mapping has no image or textual evidence")
            page = pages[match.page_index]
            if match.region and (
                match.region.bottom_right.x > page.width
                or match.region.bottom_right.y > page.height
            ):
                raise ValueError("PDF crop exceeds rendered page dimensions")
            small = {"object", "component"}
            declared_proxy = (
                request.mode == "demo_substitution"
                and request.policy_version == "narrative-proxy-v1"
                and (match.relationship == "substitution")
                and (match.story_support == "documented_activity")
                and bool(match.passage_ids)
            )
            if (match.target_scale in small) != (match.source_scale in small) and (
                not declared_proxy
            ):
                raise ValueError("PDF mapping crosses incompatible physical scales")
            if request.mode == "same_site" and match.relationship != "same_object":
                raise ValueError("Same-site mode cannot silently substitute objects")
        return (payload, receipt)
