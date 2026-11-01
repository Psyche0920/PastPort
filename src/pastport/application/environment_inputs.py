"""Validate existing execution authority around explicitly injected local input reads."""

from pastport.application.execution_guard import ExecutionGuard
from pastport.application.models import ServiceError
from pastport.application.source_views import SourceViews
from pastport.domain.story_inputs import EnvironmentReadRequest, EnvironmentSnapshot
from pastport.ports.modules import ExecutionContext
from pastport.ports.story_inputs import MatchedEnvironmentReader


class GuardedEnvironmentReader:
    def __init__(self, guard: ExecutionGuard, reader: MatchedEnvironmentReader) -> None:
        self.guard = guard
        self.reader = reader

    async def read(
        self, request: EnvironmentReadRequest, context: ExecutionContext
    ) -> EnvironmentSnapshot:
        run, _ = self.guard.validate(context)
        if request.project_id != context.metadata.project_id:
            raise ServiceError(
                "ENVIRONMENT_SCOPE_MISMATCH", "Environment belongs to another project", 403
            )
        SourceViews.source(
            run,
            request.source_ref.artifact_id,
            request.source_ref.content_version,
            request.source_ref.sha256,
        )
        result = EnvironmentSnapshot.model_validate(await self.reader.read(request, context))
        run, _ = self.guard.validate(context)
        SourceViews.source(
            run,
            request.source_ref.artifact_id,
            request.source_ref.content_version,
            request.source_ref.sha256,
        )
        if (
            result.project_id != request.project_id
            or result.environment_id != request.environment_id
            or result.import_manifest_sha256 != request.import_manifest_sha256
            or result.source_pdf_sha256 != request.source_pdf_sha256
            or (
                request.expected_content_revision is not None
                and result.content_revision != request.expected_content_revision
            )
            or (
                request.expected_spatial_revision is not None
                and result.spatial_revision != request.expected_spatial_revision
            )
            or (
                request.expected_metric_revision is not None
                and (
                    result.metric_spatial is None
                    or result.metric_spatial.revision != request.expected_metric_revision
                )
            )
        ):
            raise ServiceError(
                "ENVIRONMENT_SNAPSHOT_CHANGED",
                "Input snapshot differs from the requested identity or revision",
            )
        return result
