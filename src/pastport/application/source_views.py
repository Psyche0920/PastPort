"""Read registered source bytes and saved extraction records without research/model calls."""

from pydantic import ValidationError

from pastport.application.models import RunRecord, ServiceError
from pastport.application.preview_service import PreviewService
from pastport.application.resources import VerifiedResourceReader
from pastport.domain.common import CanonicalSerializer
from pastport.domain.evidence import EvidencePackage, Source, SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import SourceDocument
from pastport.domain.resources import ResourceData, ResourceReference
from pastport.ports.editorial import EditorialRepository


class SourceViews:
    def __init__(
        self, repository: EditorialRepository, resources: VerifiedResourceReader | None
    ) -> None:
        self.repository = repository
        self.resources = resources

    @staticmethod
    def source(run: RunRecord, source_id: str, version: str, digest: str) -> Source:
        sources: tuple[Source, ...] = ()
        # The latest evidence snapshot supersedes earlier discovery inventories.
        if any(
            item.reference.artifact_id == run.state.run_id + ":evidence" for item in run.artifacts
        ):
            sources = PreviewService.current(run, "evidence", EvidencePackage)[1].sources
        elif any(
            item.reference.artifact_id == run.state.run_id + ":index" for item in run.artifacts
        ):
            sources = PreviewService.current(run, "index", SourceIndexDraft)[1].sources
        elif any(
            item.reference.artifact_id == run.state.run_id + ":inventory" for item in run.artifacts
        ):
            sources = PreviewService.current(run, "inventory", SourceManifestDraft)[1].sources
        source = next(
            (
                item
                for item in sources
                if item.source_id == source_id
                and item.version == version
                and item.file_sha256 == digest
            ),
            None,
        )
        if source is None:
            raise ServiceError(
                "RESOURCE_NOT_REGISTERED", "Source version and hash are not in this run", 404
            )
        return source

    def content(self, run: RunRecord, source: Source) -> ResourceData:
        if self.resources is None:
            raise ServiceError("RESOURCE_UNAVAILABLE", "Source reader is not configured", 503)
        try:
            return self.resources.read(
                ResourceReference(
                    project_id=run.state.project_id,
                    resource_id=source.source_id,
                    kind="source",
                    version=source.version,
                    sha256=source.file_sha256,
                    source_uri=source.uri,
                ),
                20 * 1024 * 1024,
            )
        except ServiceError as error:
            if error.code == "RESOURCE_NOT_REGISTERED":
                raise ServiceError(
                    error.code, "Source bytes are not registered in this scope", 404
                ) from error
            raise

    def document(self, run: RunRecord, source: Source) -> SourceDocument:
        # Missing extraction is not a license to reconstruct original text from claims.
        try:
            self.content(run, source)
        except ServiceError as error:
            if error.code not in ("RESOURCE_UNAVAILABLE", "RESOURCE_NOT_REGISTERED"):
                raise
            return SourceDocument(source=source, fragments=(), status="inaccessible")
        artifacts = list(run.artifacts)
        for summary in self.repository.execution_summaries(run.state.run_id):
            if summary.artifact_ref is not None and summary.artifact_ref.kind == "report":
                stored = self.repository.execution_artifact(run.state.run_id, summary.artifact_ref)
                if stored is not None:
                    artifacts.append(stored)
        for artifact in reversed(artifacts):
            if artifact.reference.kind != "report":
                continue
            try:
                document = SourceDocument.model_validate_json(artifact.payload_json)
            except ValidationError:
                # Most reports have another typed shape, such as validation or narrative review.
                continue
            if document.source != source:
                continue
            if (
                artifact.reference.project_id != run.state.project_id
                or CanonicalSerializer.digest(document) != artifact.reference.sha256
                or any(
                    (item.locator.source_id, item.locator.source_version, item.locator.file_sha256)
                    != (source.source_id, source.version, source.file_sha256)
                    for item in document.fragments
                )
            ):
                raise ServiceError(
                    "ARTIFACT_CHANGED", "Saved original text failed its identity or hash"
                )
            return document
        return SourceDocument(
            source=source,
            fragments=(),
            status="needs_ocr" if source.extraction_state == "needs_ocr" else "failed",
        )
