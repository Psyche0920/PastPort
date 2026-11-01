"""Registered-source reading and deterministic local tools, bounded by frozen questions."""

import asyncio
import hashlib
from typing import Literal

from pastport.application.execution_guard import ExecutionGuard
from pastport.application.execution_models import ExecutionReceipt
from pastport.application.models import ServiceError, StoredArtifact
from pastport.application.reliability import OperationReservation, Usage, UsageSettlement
from pastport.application.resources import VerifiedResourceReader
from pastport.domain.common import ArtifactRef, CanonicalSerializer, SourceLocator
from pastport.domain.modules import LocatedText, SourceDocument, ToolResult
from pastport.domain.resources import ResourceReference
from pastport.domain.workflow import ToolRequest
from pastport.ports.modules import ExecutionContext
from pastport.ports.resources import ResourceReader
from pastport.ports.source_text import SourceTextError, SourceTextExtractor


class SharedSourceReader:
    def __init__(
        self,
        guard: ExecutionGuard,
        resources: ResourceReader | None,
        source_text_extractor: SourceTextExtractor | None = None,
    ) -> None:
        self.guard = guard
        self.source_text_extractor = source_text_extractor
        self.resources = VerifiedResourceReader(resources) if resources is not None else None

    def operation(self, source_ref: ArtifactRef, context: ExecutionContext) -> tuple[str, str, str]:
        digest = CanonicalSerializer.digest(source_ref)
        if self.source_text_extractor is not None:
            digest = hashlib.sha256(
                (digest + ":" + self.source_text_extractor.identity).encode("utf-8")
            ).hexdigest()
        group = self.guard.group(context, "fetch")
        return group + digest[:32], digest, group

    def reference(self, source_ref: ArtifactRef, context: ExecutionContext) -> ArtifactRef:
        operation_id, _, _ = self.operation(source_ref, context)
        receipt = self.guard.database.execution_receipt(operation_id)
        if receipt is None or receipt.artifact is None:
            raise ServiceError("SOURCE_UNAVAILABLE", "No source document receipt exists")
        return receipt.artifact.reference

    async def read(self, source_ref: ArtifactRef, context: ExecutionContext) -> SourceDocument:
        request = self.guard.question(context)
        if "read_source" not in context.metadata.allowed_tools:
            raise ServiceError(
                "TOOL_NOT_ALLOWED", "Source reads are not permitted in this stage", 403
            )
        source = next(
            (
                s
                for s in request.index.sources
                if s.source_id == source_ref.artifact_id
                and s.version == source_ref.content_version
                and s.file_sha256 == source_ref.sha256
            ),
            None,
        )
        if (
            source is None
            or source_ref.kind != "source"
            or source_ref.project_id != context.metadata.project_id
        ):
            raise ServiceError(
                "SOURCE_NOT_REGISTERED", "Source is not registered in the active question"
            )
        operation_id, input_hash, group = self.operation(source_ref, context)
        database = self.guard.database
        receipt = database.execution_receipt(operation_id)
        if receipt is not None and receipt.settlement is not None:
            database.finish_operation(
                operation_id, receipt.model_dump_json(), 0, receipt.settlement
            )
        cached = database.operation_result(operation_id, input_hash)
        if cached is not None:
            receipt = ExecutionReceipt.model_validate_json(cached)
            assert receipt.artifact is not None
            return SourceDocument.model_validate_json(receipt.artifact.payload_json)
        if self.resources is None:
            raise ServiceError("TOOL_UNAVAILABLE", "No registered resource reader is configured")
        database.reserve_operation(
            OperationReservation(
                operation_id=operation_id,
                run_id=context.metadata.run_id,
                input_hash=input_hash,
                reserved=Usage(fetch_requests=1),
                price_reference="registered-local-source",
                group_key=group,
                maximum_group_operations=4,
            )
        )
        try:
            resource = await asyncio.wait_for(
                asyncio.to_thread(
                    self.resources.read,
                    ResourceReference(
                        project_id=source_ref.project_id,
                        resource_id=source.source_id,
                        kind="source",
                        sha256=source.file_sha256,
                        version=source.version,
                        source_uri=source.uri,
                    ),
                    self.guard.binding.settings.maximum_source_bytes,
                ),
                self.guard.timeout(context),
            )
            fragments: tuple[LocatedText, ...] = ()
            status: Literal["read", "inaccessible", "needs_ocr", "failed"]
            if resource.content.startswith(b"%PDF"):
                status = "needs_ocr"
            else:
                try:
                    text = resource.content.decode("utf-8")
                    fragments = tuple(
                        LocatedText(
                            locator=SourceLocator(
                                source_id=source.source_id,
                                source_version=source.version,
                                file_sha256=source.file_sha256,
                                page_index=None,
                                printed_page=None,
                                paragraph_or_region="utf8-offset-" + str(offset),
                            ),
                            text=text[offset : offset + 10000],
                        )
                        for offset in range(0, len(text), 10000)
                        if text[offset : offset + 10000].strip()
                    )
                    status = "read" if fragments else "inaccessible"
                except UnicodeError:
                    status = "failed"
            document = SourceDocument(source=source, fragments=fragments, status=status)
            if resource.content.startswith(b"%PDF") and self.source_text_extractor is not None:
                try:
                    document = await self.source_text_extractor.extract(
                        source,
                        resource.content,
                        timeout_seconds=self.guard.timeout(context),
                        cancellation=context.cancellation,
                    )
                except SourceTextError as error:
                    raise ServiceError(error.code, str(error)) from error
                if document.source != source or any(
                    (part.locator.source_id, part.locator.source_version, part.locator.file_sha256)
                    != (source.source_id, source.version, source.file_sha256)
                    for part in document.fragments
                ):
                    raise ServiceError(
                        "SOURCE_IDENTITY_MISMATCH",
                        "Extractor changed the registered source or locator",
                    )
            self.guard.validate(context)
            reference = ArtifactRef(
                artifact_id=operation_id,
                project_id=source_ref.project_id,
                kind="report",
                schema_version="0.1.0",
                content_version=CanonicalSerializer.digest(document)[:24],
                sha256=CanonicalSerializer.digest(document),
            )
            receipt = ExecutionReceipt(
                artifact=StoredArtifact(
                    reference=reference, payload_json=document.model_dump_json()
                ),
                settlement=UsageSettlement(actual=Usage(fetch_requests=1)),
            )
            database.save_execution_receipt(operation_id, context.metadata.run_id, receipt)
            assert receipt.settlement is not None
            database.finish_operation(
                operation_id, receipt.model_dump_json(), 0, receipt.settlement
            )
        except BaseException:
            database.fail_operation(operation_id, 0)
            raise
        self.guard.validate(context)
        return document


class SharedToolExecutor:
    def __init__(self, guard: ExecutionGuard, sources: SharedSourceReader) -> None:
        self.guard = guard
        self.sources = sources

    async def execute(self, request: ToolRequest, context: ExecutionContext) -> ToolResult:
        question = self.guard.question(context)
        if request.kind not in context.metadata.allowed_tools:
            raise ServiceError("TOOL_NOT_ALLOWED", "Tool is outside the server grant", 403)
        if request.question_id != question.evidence_request.request_id or not set(
            request.site_ids
        ) <= {s.site_id for s in question.index.sites}:
            raise ServiceError(
                "RESEARCH_SCOPE_INVALID", "Tool must retain its frozen question and project targets"
            )
        if request.kind == "search_web":
            raise ServiceError(
                "TOOL_UNAVAILABLE", "No approved public-web search connector is registered"
            )
        digest = CanonicalSerializer.digest(request)
        group = self.guard.group(context, "tool")
        operation_id = group + digest[:32]
        database = self.guard.database
        receipt = database.execution_receipt(operation_id)
        if receipt is not None and receipt.settlement is not None:
            database.finish_operation(
                operation_id, receipt.model_dump_json(), 0, receipt.settlement
            )
        cached = database.operation_result(operation_id, digest)
        if cached is not None:
            receipt = ExecutionReceipt.model_validate_json(cached)
            assert receipt.artifact is not None
            return ToolResult.model_validate_json(receipt.artifact.payload_json)
        database.reserve_operation(
            OperationReservation(
                operation_id=operation_id,
                run_id=context.metadata.run_id,
                input_hash=digest,
                reserved=Usage(),
                group_key=group,
                maximum_group_operations=12,
            )
        )
        try:
            references: tuple[ArtifactRef, ...] = ()
            status: Literal[
                "ok", "empty", "inaccessible", "needs_ocr", "network_error", "denied"
            ] = "empty"
            reason = "No registered locators matched the local query; original text was not read"
            if request.kind == "read_source":
                source = next(
                    (s for s in question.index.sources if s.source_id == request.source_id), None
                )
                if source is None:
                    raise ServiceError("SOURCE_NOT_REGISTERED", "Tool source is not registered")
                source_ref = ArtifactRef(
                    artifact_id=source.source_id,
                    project_id=context.metadata.project_id,
                    kind="source",
                    schema_version="0.1.0",
                    content_version=source.version,
                    sha256=source.file_sha256,
                )
                document = await self.sources.read(source_ref, context)
                references = (self.sources.reference(source_ref, context),)
                status = (
                    "ok"
                    if document.status == "read"
                    else "needs_ocr"
                    if document.status == "needs_ocr"
                    else "inaccessible"
                )
                reason = "Registered source read result: " + document.status
            else:
                query = (request.query or "").casefold()
                matched = [
                    c
                    for c in question.index.candidate_claims
                    if query in c.text.casefold()
                    and (not request.site_ids or c.site_id in request.site_ids)
                ]
                locators = [loc for claim in matched[: request.limit] for loc in claim.support]
                references = tuple(
                    dict.fromkeys(
                        ArtifactRef(
                            artifact_id=loc.source_id,
                            project_id=context.metadata.project_id,
                            kind="source",
                            schema_version="0.1.0",
                            content_version=loc.source_version,
                            sha256=loc.file_sha256,
                        )
                        for loc in locators
                    )
                )
                if references:
                    status = "ok"
                    reason = (
                        "Matched registered candidate locators; original source text was not read"
                    )
            result = ToolResult(
                request_id=operation_id, status=status, source_refs=references, reason=reason
            )
            reference = ArtifactRef(
                artifact_id=operation_id,
                project_id=context.metadata.project_id,
                kind="report",
                schema_version="0.1.0",
                content_version=CanonicalSerializer.digest(result)[:24],
                sha256=CanonicalSerializer.digest(result),
            )
            receipt = ExecutionReceipt(
                artifact=StoredArtifact(reference=reference, payload_json=result.model_dump_json()),
                settlement=UsageSettlement(actual=Usage()),
            )
            database.save_execution_receipt(operation_id, context.metadata.run_id, receipt)
            assert receipt.settlement is not None
            database.finish_operation(
                operation_id, receipt.model_dump_json(), 0, receipt.settlement
            )
        except BaseException:
            database.fail_operation(operation_id, 0)
            raise
        self.guard.validate(context)
        return result
