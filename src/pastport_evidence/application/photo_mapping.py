"""Photo-first substitution preparation; VR localization is a separate downstream consumer."""

from __future__ import annotations

import hashlib
from itertools import islice
from pathlib import Path

from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.codex_semantics import CodexSemanticGateway
from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.adapters.identity import SQLiteSceneRepository
from pastport_evidence.application.bootstrap import atomic_write
from pastport_evidence.application.document_package import DocumentPackageExporter, OutputPaths
from pastport_evidence.application.pdf_ingestion import PDFIngestionService
from pastport_evidence.application.photos import (
    PhotoInputError,
    PhotoRecognitionService,
    PhotoRegistrar,
)
from pastport_evidence.application.preparation import (
    DocumentDraft,
    MappingPreparation,
    _ActionStage,
)
from pastport_evidence.application.prompting import load_semantic_prompt
from pastport_evidence.domain.execution import SubscriptionGrant
from pastport_evidence.domain.mapping import MappedObject
from pastport_evidence.domain.models import DomainModel, ProcessingLimits, ProjectAssetRef
from pastport_evidence.domain.pdf import RegisteredPDF
from pastport_evidence.domain.photos import PhotoInventory
from pastport_evidence.domain.recognition import RecognitionResult
from pastport_evidence.ports.execution import SemanticTransport
from pastport_evidence.ports.pdf import PDFDocumentReader
from pastport_evidence.workflow.graph import FixedStage, FixedWorkflow, StageJournal, StageOutput


class PreparedDocuments(DomainModel):
    """Private preparation checkpoint used to create documents, not an exported interface."""

    project_id: str
    input_binding: str
    source: ProjectAssetRef
    inventory: PhotoInventory
    objects: tuple[MappedObject, ...]
    gaps: tuple[str, ...]


class PhotoMappingWorkflow:
    def __init__(self, reader: PDFDocumentReader, transport: SemanticTransport) -> None:
        self.reader, self.transport = reader, transport

    def run(
        self,
        pdf: Path,
        photo_folder: Path,
        workspace: Path,
        grant: SubscriptionGrant,
        run_id: str,
        large_pdf: bool = False,
    ) -> tuple[StageOutput, ...]:
        if (workspace / "tour.json").exists():
            raise PhotoInputError("Use a dedicated document-generation workspace")
        limits = ProcessingLimits(
            pdf_max_bytes=(512 if large_pdf else 64) * 1024 * 1024,
        )
        if (
            not pdf.is_file()
            or pdf.is_symlink()
            or not 0 < pdf.stat().st_size <= limits.pdf_max_bytes
        ):
            raise PhotoInputError("PDF missing or exceeds its declared input profile")
        if not photo_folder.is_dir() or photo_folder.is_symlink():
            raise PhotoInputError("Photo folder is missing or unsafe")
        paths = tuple(islice(photo_folder.rglob("*"), 1001))
        if len(paths) > 1000:
            raise PhotoInputError("Photo directory exceeds the bounded scan limit")
        paths = tuple(sorted(paths))
        if any(p.is_symlink() for p in paths):
            raise PhotoInputError("Photo folders cannot contain symbolic links")
        photos = tuple(p for p in paths if p.is_file() and p.name not in (".DS_Store", "Thumbs.db"))
        if not 1 <= len(photos) <= 100:
            raise PhotoInputError("Supply 1-100 ordinary photographs")
        if any(p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp") for p in photos):
            raise PhotoInputError("Photo folder accepts JPEG, PNG and WebP only")
        if (
            any(p.stat().st_size > 30 * 1024 * 1024 for p in photos)
            or sum(p.stat().st_size for p in photos) > 200 * 1024 * 1024
        ):
            raise PhotoInputError("Photos exceed per-file or total limits")
        digest = hashlib.sha256(b"photo-documents-v1")
        for prompt in (
            load_semantic_prompt("photo_inspection", "v1"),
            load_semantic_prompt("pdf_matching", "v2"),
            load_semantic_prompt("evidence_association", "v2"),
        ):
            digest.update(prompt.encode())
        expected: dict[Path, str] = {}
        for path in (pdf, *photos):
            file_hash = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    file_hash.update(block)
            expected[path] = file_hash.hexdigest()
            digest.update(file_hash.digest())
            if path != pdf:
                digest.update(path.relative_to(photo_folder).as_posix().encode())
        digest.update(grant.model_dump_json().encode())
        binding = "photo-mapping:" + digest.hexdigest()
        artifacts = workspace / "runs" / digest.hexdigest()
        artifacts.mkdir(parents=True, exist_ok=True)
        assets = LocalAssetStore(workspace / "assets")
        executor = SubscriptionExecutor(
            workspace / "codex-executions.sqlite3", grant, self.transport
        )
        preparation = MappingPreparation(
            workspace=workspace,
            artifacts=artifacts,
            grant=grant,
            mode="demo_substitution",
            binding=binding,
            assets=assets,
            executor=executor,
            mapping_prompt_version="v2",
            evidence_prompt_version="v2",
        )

        def ingest() -> StageOutput:
            document_path = artifacts / "pdf.json"
            if document_path.exists():
                document = RegisteredPDF.model_validate_json(document_path.read_bytes())
            else:
                document = PDFIngestionService(assets, self.reader).register_and_extract(
                    grant.project_id, pdf, limits
                )
                atomic_write(document_path, document.model_dump_json())
            if document.source.asset.sha256 != expected[pdf]:
                raise PhotoInputError("PDF changed after immutable input binding")
            photo_path = artifacts / "photos.json"
            if photo_path.exists():
                registered = PhotoInventory.model_validate_json(photo_path.read_bytes())
            else:
                registered = PhotoInventory(
                    photos=PhotoRegistrar(assets).register(grant.project_id, photos)
                )
                atomic_write(photo_path, registered.model_dump_json())
            if tuple(p.original.asset.sha256 for p in registered.photos) != tuple(
                expected[p] for p in photos
            ):
                raise PhotoInputError("Photos changed after immutable input binding")
            return StageOutput(references=(document.source.asset.resource_id, "artifact:photos"))

        def recognize() -> StageOutput:
            photo_input = PhotoInventory.model_validate_json(
                (artifacts / "photos.json").read_bytes()
            )
            inventory = PhotoRecognitionService(
                SQLiteSceneRepository(workspace / "identities.sqlite3"),
                CodexSemanticGateway(executor, assets),
                assets,
            ).run(
                grant.project_id,
                photo_input.photos,
                artifacts,
                grant.grant_ref,
                grant.model_id,
                executor.remaining_calls(),
            )
            gaps = list(inventory.gaps)
            for observation in inventory.observations:
                if observation.identity_state == "uncertain":
                    gaps.append(
                        f"photo_identity_uncertain:{observation.object_id}:{observation.photo.photo_id}"
                    )
            recognized = RecognitionResult(
                entities=inventory.entities,
                calls_used=len(inventory.receipt_refs),
                gaps=tuple(gaps),
            )
            atomic_write(artifacts / "recognition.json", recognized.model_dump_json())
            return StageOutput(references=("artifact:photo-inventory",), gaps=tuple(gaps))

        def export() -> StageOutput:
            draft = DocumentDraft.model_validate_json(
                (artifacts / "review-draft.json").read_bytes()
            )
            inventory = PhotoInventory.model_validate_json(
                (artifacts / "photo-inventory.json").read_bytes()
            )
            objects = tuple(
                obj.model_copy(
                    update={
                        "photo_observations": tuple(
                            o for o in inventory.observations if o.object_id == obj.entity.object_id
                        )
                    }
                )
                for obj in draft.objects
            )
            document = RegisteredPDF.model_validate_json((artifacts / "pdf.json").read_bytes())
            bundle = PreparedDocuments(
                project_id=grant.project_id,
                input_binding=binding,
                source=document.source,
                inventory=inventory,
                objects=objects,
                gaps=draft.gaps,
            )
            destination = DocumentPackageExporter(assets).write(
                workspace / "exports", bundle, document
            )
            atomic_write(
                artifacts / "export-result.json",
                OutputPaths(
                    pdf=str(destination / "mapping.pdf"),
                    idml=str(destination / "mapping.idml"),
                    status="completed_with_gaps" if draft.gaps else "completed",
                    gaps=draft.gaps,
                ).model_dump_json(),
            )
            return StageOutput(
                references=("artifact:mapping-pdf", "artifact:mapping-idml"), gaps=draft.gaps
            )

        stages = tuple(
            FixedStage(name, _ActionStage(action))
            for name, action in (
                ("ingest_photos", ingest),
                ("recognize_photos", recognize),
                ("map_pdf", preparation.map_pdf),
                ("evidence", preparation.evidence),
                ("export_mapping", export),
            )
        )
        results = FixedWorkflow(
            StageJournal(workspace / "stages.sqlite3"), stages, "photo-documents-v1"
        ).run(grant.project_id, run_id, binding)
        result_path = artifacts / "export-result.json"
        output = OutputPaths.model_validate_json(result_path.read_bytes())
        DocumentPackageExporter.validate(Path(output.pdf).parent)
        atomic_write(workspace / "result.json", output.model_dump_json())
        return results
