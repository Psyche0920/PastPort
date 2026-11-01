"""Validate persisted server grants before any shared child operation."""

import hashlib
import json
from datetime import UTC, datetime

from pastport.application.execution_models import ExecutionBinding, ExecutionGrant, ModelPolicy
from pastport.application.models import LocalExecutionPolicy, RunRecord, ServiceError
from pastport.application.reliability import ReviewAuthority
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.modules import ResearchRequest
from pastport.domain.workflow import RemainingLimits
from pastport.ports.editorial import EditorialRepository
from pastport.ports.modules import ExecutionContext


class ExecutionGuard:
    def __init__(
        self, database: EditorialRepository, binding: ExecutionBinding, authority: ReviewAuthority
    ) -> None:
        self.database = database
        self.binding = binding
        self.authority = authority
        self.binding_hash = CanonicalSerializer.digest(binding)

    def validate(self, context: ExecutionContext) -> tuple[RunRecord, ExecutionGrant]:
        metadata = context.metadata
        grant = self.database.execution_grant(metadata.budget_reservation_id)
        if grant.metadata != metadata:
            raise ServiceError(
                "EXECUTION_NOT_AUTHORIZED", "Execution context differs from its server grant", 403
            )
        run = self.database.run(metadata.run_id)
        if run.state.status == "cancelled":
            raise ServiceError("RUN_CANCELLED", "Run was cancelled")
        if (
            run.state.status != "running"
            or run.state.project_id != metadata.project_id
            or metadata.actor_id != run.created_by
            or metadata.policy_ref != run.state.policy_ref
            or not metadata.operation_id.endswith(":" + run.state.node)
        ):
            raise ServiceError(
                "EXECUTION_NOT_AUTHORIZED", "The grant is not active for this stage", 403
            )
        self.authority.actor(metadata.actor_id, metadata.project_id, "editor")
        policy = LocalExecutionPolicy(
            environment=run.environment,
            external_model_calls=any(m.provider != "fake" for m in self.binding.settings.models),
            external_tools=self.binding.settings.allowed_tools,
            execution_config_hash=self.binding_hash,
        )
        if CanonicalSerializer.digest(policy) != run.state.policy_ref.sha256:
            raise ServiceError(
                "RUN_VERSION_UNSUPPORTED", "Execution configuration changed since run creation"
            )
        stored_binding = next(
            (
                a
                for a in run.artifacts
                if a.reference.artifact_id == run.state.run_id + ":execution-binding"
            ),
            None,
        )
        if (
            stored_binding is None
            or stored_binding.reference.sha256 != self.binding_hash
            or stored_binding.payload_json != self.binding.model_dump_json()
        ):
            raise ServiceError(
                "RUN_VERSION_UNSUPPORTED", "Persisted execution binding is missing or changed"
            )
        parent = next(
            (
                e
                for e in self.database.budget(metadata.run_id).entries
                if e.reservation_id == metadata.budget_reservation_id
            ),
            None,
        )
        if (
            parent is None
            or parent.operation_id != metadata.operation_id
            or parent.state != "reserved"
        ):
            raise ServiceError(
                "EXECUTION_NOT_AUTHORIZED", "The parent execution is no longer active", 403
            )
        self.database.operation_result(metadata.operation_id, metadata.execution_key)
        context.cancellation.raise_if_cancelled()
        if metadata.deadline <= datetime.now(UTC):
            raise ServiceError("EXECUTION_DEADLINE", "Execution deadline expired")
        return run, grant

    def remaining(self, context: ExecutionContext) -> RemainingLimits:
        self.validate(context)
        budget = self.database.budget(context.metadata.run_id)

        def left(field: str) -> int:
            return max(
                0,
                int(getattr(budget.limit, field))
                - int(getattr(budget.used, field))
                - int(getattr(budget.held, field)),
            )

        return RemainingLimits(
            model_requests=left("model_requests"),
            input_tokens=left("input_tokens"),
            output_tokens=left("output_tokens"),
            search_requests=left("search_requests"),
            fetch_requests=left("fetch_requests"),
            active_seconds=max(
                0, int((context.metadata.deadline - datetime.now(UTC)).total_seconds())
            ),
            cost_microusd=left("cost_microusd"),
        )

    def question(self, context: ExecutionContext) -> ResearchRequest:
        run, grant = self.validate(context)
        if run.state.node != "research_evidence" or not run.control.research_rounds:
            raise ServiceError(
                "TOOL_NOT_ALLOWED", "Tools are restricted to the active research question", 403
            )
        request = ResearchRequest.model_validate_json(grant.request_json)
        active = run.control.research_rounds[-1]
        if active.completed or request.evidence_request not in active.requests:
            raise ServiceError(
                "RESEARCH_SCOPE_INVALID", "Question does not belong to the frozen round"
            )
        return request

    def group(self, context: ExecutionContext, kind: str) -> str:
        run, _ = self.validate(context)
        identity = context.metadata.operation_id
        if run.state.node == "research_evidence":
            identity = (
                run.control.research_rounds[-1].round_id
                + ":"
                + self.question(context).evidence_request.request_id
            )
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return context.metadata.run_id + ":shared:" + digest + ":" + kind + ":"

    def timeout(self, context: ExecutionContext) -> float:
        self.validate(context)
        return max(
            0.001,
            min(
                float(self.binding.settings.timeout_seconds),
                (context.metadata.deadline - datetime.now(UTC)).total_seconds(),
            ),
        )

    def model(self, context: ExecutionContext) -> ModelPolicy:
        run, _ = self.validate(context)
        role = (
            "research" if run.state.node in ("extract_candidates", "research_evidence") else "story"
        )
        if run.state.node not in (
            "extract_candidates",
            "research_evidence",
            "discover_story",
            "draft_narrative",
        ):
            raise ServiceError("MODEL_NOT_ALLOWED", "Models are not allowed in this stage", 403)
        policy = next((m for m in self.binding.settings.models if m.role == role), None)
        if policy is None:
            raise ServiceError("MODEL_UNAVAILABLE", "No shared model is configured for this role")
        return policy

    def artifact(self, reference: ArtifactRef, context: ExecutionContext) -> str:
        run, _ = self.validate(context)
        if reference.project_id != run.state.project_id:
            raise ServiceError("PROJECT_MISMATCH", "Cross-project model input is forbidden", 403)
        artifact = (
            next((a for a in run.artifacts if a.reference == reference), None)
            if reference in context.metadata.input_refs
            else None
        )
        if artifact is None and any(
            reference.artifact_id.startswith(self.group(context, kind))
            for kind in ("fetch", "tool", "loop")
        ):
            artifact = self.database.execution_artifact(run.state.run_id, reference)
        if artifact is None:
            raise ServiceError("ARTIFACT_MISSING", "Input is not a registered run artifact")
        payload = json.loads(artifact.payload_json)
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if hashlib.sha256(canonical).hexdigest() != reference.sha256:
            raise ServiceError("ARTIFACT_CHANGED", "Registered model input failed its hash")
        return artifact.payload_json
