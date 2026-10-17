"""One bounded research role: durable steps, no tool-invented permissions or new questions."""

import hashlib
import json

from pastport.application.execution_guard import ExecutionGuard
from pastport.application.execution_models import ExecutionReceipt
from pastport.application.model_gateway import SharedModelGateway
from pastport.application.models import ServiceError, StoredArtifact
from pastport.application.reliability import OperationReservation, Usage, UsageSettlement
from pastport.application.source_tools import SharedToolExecutor
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract, Sha256
from pastport.domain.modules import EvidenceFindings, SourceDocument
from pastport.domain.workflow import SkillResult
from pastport.ports.modules import ExecutionContext, ModelRequest


class ResearchProgress(Contract):
    initial_hash: Sha256
    input_refs: tuple[ArtifactRef, ...]
    observed_documents: tuple[Sha256, ...]
    no_progress: int


class SharedResearchExecutor:
    def __init__(
        self, guard: ExecutionGuard, models: SharedModelGateway, tools: SharedToolExecutor
    ) -> None:
        self.guard, self.models, self.tools = guard, models, tools

    async def run(
        self, request: ModelRequest[SkillResult[EvidenceFindings]], context: ExecutionContext
    ) -> SkillResult[EvidenceFindings]:
        question = self.guard.question(context)
        seed = dict(
            role=request.role,
            input_refs=[r.model_dump(mode="json") for r in request.input_refs],
            skill_ref=request.skill_ref.model_dump(mode="json"),
            schema=request.output_model.model_json_schema(),
        )
        initial_hash = hashlib.sha256(json.dumps(seed, sort_keys=True).encode()).hexdigest()
        progress = ResearchProgress(
            initial_hash=initial_hash,
            input_refs=request.input_refs,
            observed_documents=(),
            no_progress=0,
        )
        database = self.guard.database
        group = self.guard.group(context, "loop")
        for step in range(6):
            operation_id = group + str(step)
            receipt = database.execution_receipt(operation_id)
            if receipt is not None and receipt.settlement is not None:
                database.finish_operation(
                    operation_id, receipt.model_dump_json(), 0, receipt.settlement
                )
                assert receipt.artifact is not None
                progress = ResearchProgress.model_validate_json(receipt.artifact.payload_json)
                if progress.initial_hash != initial_hash:
                    raise ServiceError("EXECUTION_INPUT_CHANGED", "Research loop inputs changed")
            else:
                call = ModelRequest(
                    role=request.role,
                    input_refs=progress.input_refs,
                    skill_ref=request.skill_ref,
                    output_model=request.output_model,
                )
                result = (await self.models.generate(call, context)).payload
                if result.decision != "request_tool":
                    return result
                if (
                    result.tool_request is None
                    or result.tool_request.question_id != question.evidence_request.request_id
                ):
                    raise ServiceError(
                        "RESEARCH_SCOPE_INVALID", "Model requested a tool for another question"
                    )
                tool = await self.tools.execute(result.tool_request, context)
                documents = list(progress.observed_documents)
                refs = list(progress.input_refs)
                for reference in tool.source_refs:
                    if reference.kind != "report":
                        continue
                    artifact = database.execution_artifact(context.metadata.run_id, reference)
                    if artifact is None:
                        continue
                    document = SourceDocument.model_validate_json(artifact.payload_json)
                    if (
                        document.status == "read"
                        and document.fragments
                        and document.source.file_sha256 not in documents
                    ):
                        documents.append(document.source.file_sha256)
                    if reference not in refs:
                        refs.append(reference)
                # Persist the tool observation itself even when it contains only leads/no result.
                tool_digest = CanonicalSerializer.digest(result.tool_request)
                tool_op = self.guard.group(context, "tool") + tool_digest[:32]
                tool_receipt = database.execution_receipt(tool_op)
                assert tool_receipt is not None and tool_receipt.artifact is not None
                if tool_receipt.artifact.reference not in refs:
                    refs.append(tool_receipt.artifact.reference)
                next_progress = ResearchProgress(
                    initial_hash=initial_hash,
                    input_refs=tuple(refs),
                    observed_documents=tuple(documents),
                    no_progress=0
                    if len(documents) > len(progress.observed_documents)
                    else progress.no_progress + 1,
                )
                digest = CanonicalSerializer.digest(progress)
                database.reserve_operation(
                    OperationReservation(
                        operation_id=operation_id,
                        run_id=context.metadata.run_id,
                        input_hash=digest,
                        reserved=Usage(),
                        group_key=group,
                        maximum_group_operations=6,
                    )
                )
                reference = ArtifactRef(
                    artifact_id=operation_id,
                    project_id=context.metadata.project_id,
                    kind="report",
                    schema_version="0.1.0",
                    content_version=CanonicalSerializer.digest(next_progress)[:24],
                    sha256=CanonicalSerializer.digest(next_progress),
                )
                receipt = ExecutionReceipt(
                    artifact=StoredArtifact(
                        reference=reference, payload_json=next_progress.model_dump_json()
                    ),
                    settlement=UsageSettlement(actual=Usage()),
                )
                database.save_execution_receipt(operation_id, context.metadata.run_id, receipt)
                assert receipt.settlement is not None
                database.finish_operation(
                    operation_id, receipt.model_dump_json(), 0, receipt.settlement
                )
                progress = next_progress
            if progress.no_progress >= 2:
                raise ServiceError(
                    "RESEARCH_NO_PROGRESS",
                    "Two tool steps produced no new readable source evidence",
                )
        raise ServiceError("RESEARCH_OPERATION_LIMIT", "Six research model decisions are exhausted")
