"""Bind existing semantic ports to one grant-scoped, metered Codex executor."""

import json
from typing import Literal, TypeVar

from pastport_pdf_vr.adapters.execution import SubscriptionExecutor
from pastport_pdf_vr.adapters.structured_output import StrictOutputSchema
from pastport_pdf_vr.application.prompting import load_semantic_prompt
from pastport_pdf_vr.application.recognition import SceneRecognitionService
from pastport_pdf_vr.domain.build import PDFMatchPayload, PDFMatchRequest
from pastport_pdf_vr.domain.evidence import (
    DraftRequest,
    EvidencePayload,
    EvidenceProposal,
    EvidenceSelection,
    PopupPayload,
    PopupProposal,
)
from pastport_pdf_vr.domain.execution import ExecutionDenied, ExecutionInput
from pastport_pdf_vr.domain.models import DomainModel, ProjectAssetRef
from pastport_pdf_vr.domain.recognition import (
    SceneInspection,
    SceneInspectionPayload,
    SceneInspectionRequest,
)
from pastport_pdf_vr.ports.assets import AssetStore

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
    ) -> None:
        self._executor, self._assets = executor, assets
        self._images = {item.image_id: item.image for item in evidence_images}
        if len(self._images) != len(evidence_images):
            raise ValueError("Source crop IDs must be unique")

    def _execute(
        self,
        kind: Literal["scene_inspection", "evidence_association", "popup_draft", "pdf_matching"],
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
        return output.model_validate_json(result.payload_json), result.receipt_ref

    def inspect(self, request: SceneInspectionRequest) -> SceneInspection:
        if request.project_id != self._executor.grant.project_id:
            raise ExecutionDenied("Scene request belongs to another project")
        payload, receipt = self._execute(
            "scene_inspection",
            request,
            SceneInspectionPayload,
            tuple(image.image for image in request.images),
            request.grant_ref,
            request.model_id,
            request.prompt_version,
            request.policy_version,
        )
        result = SceneInspection(**payload.model_dump(), receipt_ref=receipt)
        SceneRecognitionService.validate_inspection(request, result)
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
        payload, receipt = self._execute(
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

    def draft(self, request: DraftRequest) -> PopupProposal:
        self._source_images(request.selection)  # Validate project and crop binding before dispatch.
        selection = request.selection
        payload, receipt = self._execute(
            "popup_draft",
            request,
            PopupPayload,
            (),
            selection.grant_ref,
            selection.model_id,
            selection.prompt_version,
            selection.policy_version,
        )
        return PopupProposal(**payload.model_dump(), receipt_ref=receipt)

    def match_pdf(self, request: PDFMatchRequest) -> tuple[PDFMatchPayload, str]:
        payload, receipt = self._execute(
            "pdf_matching",
            request,
            PDFMatchPayload,
            tuple(page.image for page in request.pages),
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
            if not match.region and not match.passage_ids:
                raise ValueError("PDF mapping has no image or textual evidence")
            page = pages[match.page_index]
            if match.region and (
                match.region.bottom_right.x > page.width
                or match.region.bottom_right.y > page.height
            ):
                raise ValueError("PDF crop exceeds rendered page dimensions")
            small = {"object", "component"}
            if (match.target_scale in small) != (match.source_scale in small):
                raise ValueError("PDF mapping crosses incompatible physical scales")
            if request.mode == "same_site" and match.relationship != "same_object":
                raise ValueError("Same-site mode cannot silently substitute objects")
        return payload, receipt
