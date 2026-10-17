"""Persist each stage result before graph checkpointing; human gates query business records."""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from pastport.application.activity import ActivityMeter
from pastport.application.execution_models import ExecutionGrant
from pastport.application.models import (
    LocalExecutionPolicy,
    ReviewRequest,
    RunRecord,
    ServiceError,
    StoredArtifact,
)
from pastport.application.package_loader import RuntimePackageLoader
from pastport.application.publication import PublicationService
from pastport.application.reliability import (
    ExecutionIdentity,
    OperationReservation,
    ReleaseRecord,
    ReviewAuthority,
    Usage,
    UsageSettlement,
)
from pastport.application.resources import VerifiedResourceReader
from pastport.application.routing import WorkflowRouter
from pastport.application.updates import updated
from pastport.domain.common import (
    ArtifactKind,
    ArtifactRef,
    CanonicalSerializer,
    Contract,
    FolderInput,
    VersionedPayload,
)
from pastport.domain.evidence import (
    EvidencePackage,
    RouteRecord,
    SourceIndexDraft,
    SourceManifestDraft,
)
from pastport.domain.game import RuntimeCapabilities
from pastport.domain.modules import (
    ApprovedEvidenceView,
    AssemblyRequest,
    AssemblyResult,
    CandidateSetDraft,
    DiscoverRequest,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    NarrativeDraft,
    PackageValidationRequest,
    RevisionRequest,
)
from pastport.domain.packages import (
    PackageBundle,
    ReviewSnapshot,
    ReviewTarget,
    RuntimePackage,
    ValidationReport,
)
from pastport.domain.resources import ResourceReference
from pastport.domain.workflow import ExecutionMetadata, NodeName, RemainingLimits, WorkflowError
from pastport.ports.editorial import EditorialRepository
from pastport.ports.modules import (
    AssemblyPort,
    EvidencePort,
    ExecutionContext,
    NarrativePort,
    PackageValidatorPort,
)
from pastport.ports.resources import ResourceReader
from pastport.workflow.branching import BranchRunner

if TYPE_CHECKING:
    from pastport.application.execution_runtime import ExecutionRuntime

logger = logging.getLogger(__name__)


class RunCancellation:
    def __init__(self, database: EditorialRepository, run_id: str) -> None:
        self.database = database
        self.run_id = run_id

    def raise_if_cancelled(self) -> None:
        if self.database.run(self.run_id).state.status == "cancelled":
            raise ServiceError("RUN_CANCELLED", "Run was cancelled")


class StageRunner:
    def __init__(
        self,
        database: EditorialRepository,
        releases: Path,
        resources: ResourceReader | None,
        evidence: EvidencePort | None,
        narrative: NarrativePort | None,
        assembly: AssemblyPort | None,
        validator: PackageValidatorPort | None,
        capabilities: RuntimeCapabilities,
        environment: Literal["test", "production"],
        authority: ReviewAuthority,
        package_loader: RuntimePackageLoader,
        execution: "ExecutionRuntime | None" = None,
    ) -> None:
        self.database = database
        self.releases = releases
        self.resources = VerifiedResourceReader(resources) if resources is not None else None
        self.evidence = evidence
        self.narrative = narrative
        self.assembly = assembly
        self.validator = validator
        self.capabilities = capabilities
        self.environment = environment
        self.authority = authority
        self.package_loader = package_loader
        self.execution = execution
        self.activity = ActivityMeter(database)
        self.router = WorkflowRouter(database)
        self.branches = BranchRunner(self)

    def load[Payload: Contract](self, run: RunRecord, node: str, model: type[Payload]) -> Payload:
        artifact = next(
            (
                item
                for item in reversed(run.artifacts)
                if item.reference.artifact_id == run.state.run_id + ":" + node
            ),
            None,
        )
        if artifact is None:
            raise ServiceError("ARTIFACT_MISSING", "A required stage artifact is missing")
        if (
            CanonicalSerializer.digest(model.model_validate_json(artifact.payload_json))
            != artifact.reference.sha256
        ):
            raise ServiceError("ARTIFACT_CHANGED", "Stored artifact failed its content hash")
        return model.model_validate_json(artifact.payload_json)

    def reference(self, run: RunRecord, node: str) -> ArtifactRef:
        return next(
            item.reference
            for item in reversed(run.artifacts)
            if item.reference.artifact_id == run.state.run_id + ":" + node
        )

    def save_artifact(
        self,
        run: RunRecord,
        node: str,
        kind: ArtifactKind,
        payload: Contract,
        next_node: NodeName,
        **state_changes: object,
    ) -> None:
        reference = ArtifactRef(
            artifact_id=run.state.run_id + ":" + node,
            project_id=run.state.project_id,
            kind=kind,
            schema_version="0.1.0",
            content_version=payload.content_version
            if isinstance(payload, VersionedPayload)
            else payload.package.content_version
            if isinstance(payload, NarrativeDraft)
            else CanonicalSerializer.digest(payload)[:24],
            sha256=CanonicalSerializer.digest(payload),
        )
        artifact = StoredArtifact(reference=reference, payload_json=payload.model_dump_json())
        state = updated(
            run.state,
            revision=run.state.revision + 1,
            node=next_node,
            status="running",
            **state_changes,
        )
        self.database.save(
            updated(run, state=state, artifacts=(*run.artifacts, artifact)),
            run.state.revision,
            "Completed " + node,
        )

    def context(self, run: RunRecord, operation_id: str) -> ExecutionContext:
        self.authority.actor(run.created_by, run.state.project_id, "editor")
        snapshot = self.database.budget(run.state.run_id)
        available = (
            self.activity.remaining()
            if self.activity.started is not None
            else snapshot.limit.active_milliseconds
            - snapshot.used.active_milliseconds
            - snapshot.held.active_milliseconds
        )
        remaining = available // 1000
        if remaining <= 0:
            raise ServiceError("BUDGET_EXHAUSTED", "Less than one schedulable second remains")
        metadata = ExecutionMetadata(
            project_id=run.state.project_id,
            run_id=run.state.run_id,
            operation_id=operation_id,
            execution_key=hashlib.sha256(operation_id.encode()).hexdigest(),
            input_refs=tuple(
                {item.reference.artifact_id: item.reference for item in run.artifacts}.values()
            ),
            policy_ref=run.state.policy_ref,
            skill_ref=None,
            model_config_ref=None,
            budget_reservation_id=run.state.budget_id,
            actor_id=run.created_by,
            deadline=datetime.now(UTC) + timedelta(seconds=remaining),
            remaining_limits=RemainingLimits(
                model_requests=0,
                input_tokens=0,
                output_tokens=0,
                search_requests=0,
                fetch_requests=0,
                active_seconds=remaining,
                cost_microusd=0,
            ),
            allowed_tools=(),
        )
        if self.execution is not None:
            metadata = self.execution.context(run, metadata)
        return ExecutionContext(metadata, RunCancellation(self.database, run.state.run_id))

    def call[Payload: Contract](
        self,
        run: RunRecord,
        result_type: type[ModuleResult[Payload]],
        invoke: Callable[[ExecutionContext], Awaitable[ModuleResult[Payload]]],
        *,
        request: Contract,
        unit: str = "",
    ) -> ModuleResult[Payload]:
        request_hash = CanonicalSerializer.digest(request)
        suffix = (
            ""
            if run.state.node in ("inventory_sources", "extract_candidates")
            else request_hash[:24] + ":" + unit + ":"
        )
        if run.control.retry_generation:
            suffix += "retry-" + str(run.control.retry_generation) + ":"
        operation_id = run.state.run_id + ":" + suffix + run.state.node
        request_ref = ArtifactRef(
            artifact_id="input-" + request_hash + ("-" + unit if unit else ""),
            project_id=run.state.project_id,
            kind="report",
            schema_version="0.1.0",
            content_version="1",
            sha256=request_hash,
        )
        identity = ExecutionIdentity(
            project_id=run.state.project_id,
            run_id=run.state.run_id,
            node=run.state.node,
            graph_version=run.state.graph_version,
            policy_ref=run.state.policy_ref,
            input_refs=(request_ref,),
            budget_policy=run.budget_policy,
            selection_hash=CanonicalSerializer.digest(run.selected_candidate)
            if run.selected_candidate
            else None,
        )
        input_hash = CanonicalSerializer.digest(identity)
        cached = self.database.operation_result(operation_id, input_hash)
        if cached is not None:
            result = result_type.model_validate_json(cached)
        else:
            context = self.context(run, operation_id)
            reservation_id = self.database.reserve_operation(
                OperationReservation(
                    operation_id=operation_id,
                    run_id=run.state.run_id,
                    input_hash=input_hash,
                    reserved=Usage(),
                )
            )
            context = ExecutionContext(
                updated(
                    context.metadata, execution_key=input_hash, budget_reservation_id=reservation_id
                ),
                context.cancellation,
            )
            self.database.save_grant(
                ExecutionGrant(metadata=context.metadata, request_json=request.model_dump_json())
            )

            async def bounded() -> ModuleResult[Payload]:
                return await asyncio.wait_for(
                    invoke(context), context.metadata.remaining_limits.active_seconds
                )

            try:
                result = result_type.model_validate_json(asyncio.run(bounded()).model_dump_json())
            except BaseException:
                self.database.fail_operation(operation_id, 0)
                raise
            milliseconds = 0
            self.database.finish_operation(
                operation_id,
                result.model_dump_json(),
                milliseconds,
                UsageSettlement(actual=Usage(active_milliseconds=milliseconds)),
            )
            if self.database.budget(run.state.run_id).over_limit:
                raise ServiceError("BUDGET_EXHAUSTED", "Recorded actual usage exceeded the budget")
        result_project = getattr(result.payload, "project_id", None)
        if isinstance(result.payload, NarrativeDraft):
            result_project = result.payload.package.project_id
        if (
            result.payload is not None
            and result_project is not None
            and result_project != run.state.project_id
        ):
            raise ServiceError("PROJECT_MISMATCH", "Module returned data from another project")
        if any(r.project_id != run.state.project_id for r in result.evidence_requests):
            raise ServiceError(
                "PROJECT_MISMATCH", "Module returned cross-project evidence requests"
            )
        return result

    def completed[Payload: Contract](
        self, run: RunRecord, result: ModuleResult[Payload]
    ) -> Payload | None:
        if result.outcome == "completed" and result.payload is not None:
            if any(issue.severity == "blocking" for issue in result.issues):
                run = self.branches.append(
                    run, "control-" + str(run.state.revision), "report", result
                )
                self.router.stop(run, "MODULE_REVIEW_REQUIRED", result.reason)
                return None
            return result.payload
        run = self.branches.append(run, "control-" + str(run.state.revision), "report", result)
        if result.outcome == "blocked" and any(i.code == "REVIEW_REQUIRED" for i in result.issues):
            self.router.stop(run, "MODULE_REVIEW_REQUIRED", result.reason)
            return None
        if result.outcome == "research_required":
            if not any(
                a.reference.artifact_id == run.state.run_id + ":index" for a in run.artifacts
            ):
                self.router.stop(
                    run, "RESEARCH_SCOPE_INVALID", "Research requires an indexed project scope"
                )
                return None
            self.router.research(
                run,
                result.evidence_requests,
                "discover"
                if run.selected_candidate is None
                else run.control.research_return_action,
            )
        else:
            self.router.stop(
                run,
                "MODULE_BLOCKED" if result.outcome == "blocked" else "MODULE_REVIEW_REQUIRED",
                result.reason,
                "blocked" if result.outcome == "blocked" else "needs_review",
            )
        return None

    def snapshot(self, run: RunRecord, gates: tuple[str, ...]) -> ReviewSnapshot:
        targets = tuple(
            target
            for request in run.review_requests
            if request.gate in gates
            for target in request.targets
        )
        latest = []
        decisions = self.database.reviews(run.state.run_id)
        revoked = set(self.database.revoked_reviews(run.state.run_id))
        for gate in gates:
            if set(target for target in targets if target.gate == gate) != set(
                self.review_targets(run, gate)
            ):
                raise ServiceError(
                    "REVIEW_STALE", "Review targets no longer match current artifacts"
                )
        for target in targets:
            decision = next(
                (
                    item
                    for item in reversed(decisions)
                    if (item.target_id, item.target_version, item.target_hash, item.gate)
                    == (target.target_id, target.version, target.sha256, target.gate)
                ),
                None,
            )
            if decision is not None:
                if decision.decision_id in revoked:
                    raise ServiceError("REVIEW_REVOKED", "Required approval has been revoked")
                self.authority.decision(decision, run.state.project_id)
                latest.append(decision)
        return ReviewSnapshot(
            environment=run.environment, required_targets=targets, decisions=tuple(latest)
        )

    def evidence_view(self, run: RunRecord) -> ApprovedEvidenceView:
        return ApprovedEvidenceView(
            evidence=self.load(run, "evidence", EvidencePackage),
            evidence_ref=self.reference(run, "evidence"),
            route=self.load(run, "route", RouteRecord),
            approved_route_ref=self.reference(run, "route"),
            reviews=self.snapshot(run, ("evidence",)),
        )

    def review_targets(self, run: RunRecord, gate: str) -> tuple[ReviewTarget, ...]:
        if gate == "evidence":
            evidence = self.load(run, "evidence", EvidencePackage)
            targets = [
                ReviewTarget(
                    target_id=item.claim_id,
                    version=item.version,
                    sha256=CanonicalSerializer.digest(item),
                    gate="evidence",
                )
                for item in evidence.claims
            ]
            targets.extend(
                ReviewTarget(
                    target_id=item.asset_id,
                    version=item.version,
                    sha256=CanonicalSerializer.digest(item),
                    gate="evidence",
                )
                for item in evidence.assets
            )
            for node in ("route", "evidence"):
                reference = self.reference(run, node)
                targets.append(
                    ReviewTarget(
                        target_id=reference.artifact_id,
                        version=reference.content_version,
                        sha256=reference.sha256,
                        gate="evidence",
                    )
                )
            return tuple(targets)
        node = "narrative" if gate == "narrative" else "runtime"
        reference = self.reference(run, node)
        return (
            ReviewTarget(
                target_id=reference.artifact_id,
                version=reference.content_version,
                sha256=reference.sha256,
                gate="narrative" if gate == "narrative" else "publication",
            ),
        )

    def gate(self, run_id: str, gate: str) -> bool:
        with self.activity.measure(run_id, "gate-" + gate):
            return self._gate(run_id, gate)

    def _gate(self, run_id: str, gate: str) -> bool:
        run = self.database.run(run_id)
        request_id = run_id + ":" + gate + ":" + str(run.state.revision)
        request = next((item for item in reversed(run.review_requests) if item.gate == gate), None)
        targets = self.review_targets(run, gate)
        if request is None or request.targets != targets:
            request = ReviewRequest(
                request_id=request_id,
                gate="evidence"
                if gate == "evidence"
                else "narrative"
                if gate == "narrative"
                else "publication",
                targets=targets,
            )
            state = updated(
                run.state,
                revision=run.state.revision + 1,
                status="waiting_review",
                pending_review_id=request_id,
            )
            self.database.save(
                updated(
                    run,
                    state=state,
                    review_requests=tuple(r for r in run.review_requests if r.gate != gate)
                    + (request,),
                ),
                run.state.revision,
                "Waiting for " + gate + " review",
            )
            return False
        try:
            self.snapshot(run, (gate,))
        except ValidationError:
            return False
        next_node: NodeName = (
            "draft_narrative"
            if gate == "evidence"
            else "assemble_package"
            if gate == "narrative"
            else "publish_package"
        )
        changes: dict[str, object] = {}
        if gate == "evidence":
            changes["approved_route_ref"] = self.reference(run, "route")
        self.database.save(
            updated(
                run,
                state=updated(
                    run.state,
                    revision=run.state.revision + 1,
                    node=next_node,
                    status="running",
                    pending_review_id=None,
                    pending_request_id=None,
                    **changes,
                ),
            ),
            run.state.revision,
            gate + " review accepted",
        )
        return True

    def execute(self, run_id: str, node: NodeName) -> None:
        with self.activity.measure(run_id, node):
            self._execute(run_id, node)

    def _execute(self, run_id: str, node: NodeName) -> None:
        run = self.database.run(run_id)
        if run.state.node != node or run.state.status in (
            "cancelled",
            "published",
            "needs_changes",
            "no_feasible_story",
        ):
            return
        project = self.database.project(run.state.project_id)
        if node == "register_project":
            self.database.save(
                updated(
                    run,
                    state=updated(
                        run.state,
                        revision=run.state.revision + 1,
                        node="inventory_sources",
                        status="running",
                    ),
                ),
                run.state.revision,
                "Project registered",
            )
            return
        if node == "inventory_sources":
            inventory_port = self.evidence
            if inventory_port is None:
                raise ServiceError(
                    "MODULE_NOT_CONFIGURED", "Evidence adapter is required by inventory_sources"
                )
            request = InventoryRequest(
                folder=FolderInput(
                    provider=project.provider, folder_id=project.folder_id, manifest_ref=None
                ),
                requirements=project.requirements,
                policy_ref=run.state.policy_ref,
            )
            result = self.completed(
                run,
                self.call(
                    run,
                    ModuleResult[SourceManifestDraft],
                    lambda context: inventory_port.inventory(request, context),
                    request=request,
                ),
            )
            if result is None:
                return
            self.save_artifact(run, "manifest", "source_manifest", result, "extract_candidates")
        elif node == "extract_candidates":
            index_port = self.evidence
            if index_port is None:
                raise ServiceError(
                    "MODULE_NOT_CONFIGURED", "Evidence adapter is required by extract_candidates"
                )
            manifest = self.load(run, "manifest", SourceManifestDraft)
            references = tuple(
                ArtifactRef(
                    artifact_id=item.source_id,
                    project_id=run.state.project_id,
                    kind="source",
                    schema_version="0.1.0",
                    content_version=item.version,
                    sha256=item.file_sha256,
                )
                for item in manifest.sources
            )
            index_request = IndexRequest(
                manifest=manifest, source_refs=references, requirements=project.requirements
            )
            index_response = self.call(
                run,
                ModuleResult[SourceIndexDraft],
                lambda context: index_port.index(index_request, context),
                request=index_request,
            )
            if index_response.outcome == "research_required" and index_response.payload is not None:
                run = self.branches.append(run, "index", "source_index", index_response.payload)
            index = self.completed(run, index_response)
            if index is None:
                return
            self.save_artifact(run, "index", "source_index", index, "discover_story")
        elif node == "discover_story":
            discovery_port = self.narrative
            if discovery_port is None:
                raise ServiceError(
                    "MODULE_NOT_CONFIGURED", "Narrative adapter is required by discover_story"
                )
            discover_request = DiscoverRequest(
                index=self.load(run, "index", SourceIndexDraft),
                requirements=project.requirements,
                runtime_capabilities=self.capabilities,
            )
            response = self.call(
                run,
                ModuleResult[CandidateSetDraft],
                lambda context: discovery_port.discover(discover_request, context),
                request=discover_request,
            )
            if response.payload is not None:
                known_refs = set(
                    {a.reference.artifact_id: a.reference for a in run.artifacts}.values()
                )
                index = self.load(run, "index", SourceIndexDraft)
                known_refs |= {
                    ArtifactRef(
                        artifact_id=source.source_id,
                        project_id=run.state.project_id,
                        kind="source",
                        schema_version="0.1.0",
                        content_version=source.version,
                        sha256=source.file_sha256,
                    )
                    for source in index.sources
                }
                if any(
                    ref not in known_refs
                    for candidate in response.payload.candidates
                    for ref in candidate.source_refs
                ):
                    raise ServiceError(
                        "CANDIDATE_REFERENCE_INVALID",
                        "Discovery used unregistered project evidence",
                    )
            if response.outcome == "no_feasible_story":
                run = self.branches.append(
                    run, "feasibility-" + str(run.state.revision), "report", response
                )
                self.router.no_feasible(run, response.payload, response.reason)
                return
            if (
                response.outcome in ("completed", "research_required")
                and response.payload is not None
                and response.payload.candidates
            ):
                candidates = response.payload
            else:
                completed_candidates = self.completed(run, response)
                if completed_candidates is None:
                    return
                self.router.stop(
                    run,
                    "NO_CANDIDATES",
                    "Discovery returned no candidates or actionable evidence gap",
                )
                return
            if any(issue.severity == "blocking" for issue in response.issues):
                run = self.branches.append(
                    run, "discovery-" + str(run.state.revision), "report", response
                )
                self.router.stop(run, "MODULE_REVIEW_REQUIRED", response.reason)
                return
            run = self.branches.append(
                run, "discovery-" + str(run.state.revision), "report", response
            )
            self.save_artifact(
                run,
                "candidates",
                "candidate_set",
                candidates,
                "select_candidate",
                index_ref=self.reference(run, "index"),
            )
        elif node == "research_evidence":
            self.branches.research(run)
        elif node == "draft_narrative":
            self.branches.narrative(run)
        elif node == "assemble_package":
            draft = self.load(run, "draft", NarrativeDraft)
            assembly_service = self.assembly
            if assembly_service is None:
                raise ServiceError("MODULE_NOT_CONFIGURED", "Assembly adapter is not configured")
            assembly_result = assembly_service.assemble(
                AssemblyRequest(
                    evidence=self.evidence_view(run),
                    narrative=draft.package,
                    narrative_ref=self.reference(run, "narrative"),
                    reviews=self.snapshot(run, ("evidence", "narrative")),
                    runtime_capabilities=self.capabilities,
                )
            )
            assembly_result = AssemblyResult.model_validate(assembly_result)
            built = assembly_result.package
            if (
                built.project_id != run.state.project_id
                or built.game != draft.package.game
                or built.content_version != draft.package.content_version
                or built.evidence_package_hash != self.reference(run, "evidence").sha256
                or built.narrative_package_hash != self.reference(run, "narrative").sha256
                or built.runtime_compatibility != self.capabilities
            ):
                raise ServiceError(
                    "ASSEMBLY_OUTPUT_INVALID",
                    "Assembly adapter changed the approved package dependencies or game",
                )
            self.validate_report(assembly_result.report, built)
            if self.route_validation(run, assembly_result.report):
                return
            reference = ArtifactRef(
                artifact_id=run_id + ":runtime",
                project_id=run.state.project_id,
                kind="runtime",
                schema_version="0.1.0",
                content_version=assembly_result.package.content_version,
                sha256=CanonicalSerializer.digest(assembly_result.package),
            )
            self.save_artifact(
                run,
                "runtime",
                "runtime",
                assembly_result.package,
                "validate_package",
                runtime_ref=reference,
            )
        elif node == "validate_package":
            self.verify_sources(run)
            package = self.load(run, "runtime", RuntimePackage)
            validator = self.validator
            if validator is None:
                raise ServiceError("MODULE_NOT_CONFIGURED", "Package validator is not configured")
            report = validator.validate(
                PackageValidationRequest(
                    package=package,
                    runtime_capabilities=package.runtime_compatibility,
                    checks=("schema", "references", "media_hashes"),
                )
            )
            report = ValidationReport.model_validate(report)
            self.validate_report(report, package)
            if self.route_validation(run, report):
                return
            self.save_artifact(run, "validation", "report", report, "publish_review")
        elif node == "publish_package":
            self.publish(run)

    @staticmethod
    def validate_report(report: ValidationReport, package: RuntimePackage) -> None:
        if report.artifact_hash != CanonicalSerializer.digest(package):
            raise ServiceError(
                "VALIDATION_OUTPUT_INVALID", "Validation report belongs to another package"
            )

    def route_validation(self, run: RunRecord, report: ValidationReport) -> bool:
        blocking = tuple(i for i in report.issues if i.severity == "blocking")
        if not blocking:
            return False
        run = self.branches.append(
            run, "validation-issues-" + str(run.state.revision), "report", report
        )
        reason = "; ".join(i.message + ": " + i.remediation for i in blocking)[:10000]
        owners = {i.owner for i in blocking}
        if owners == {"narrative"}:
            draft = self.load(run, "draft", NarrativeDraft)
            self.branches.request_revision(run, reason, (draft.package.game.chapter_id,))
        elif owners == {"evidence"}:
            question = self.router.research_question(run, reason, ())
            draft = self.load(run, "draft", NarrativeDraft)
            revision = RevisionRequest(
                request_id="validation-revision-" + str(run.state.revision),
                feedback=reason,
                target_ids=(draft.package.game.chapter_id,),
                reason=reason,
                locked_fields=run.locked_fields,
            )
            run = updated(run, control=updated(run.control, revision_request=revision))
            self.router.research(run, (question,), "revise")
        else:
            self.router.stop(run, "VALIDATION_REWORK_REQUIRED", reason)
        return True

    def verify_sources(self, run: RunRecord) -> None:
        if self.resources is None:
            raise ServiceError(
                "MODULE_NOT_CONFIGURED", "Resource reader is required for source verification"
            )
        for source in self.load(run, "evidence", EvidencePackage).sources:
            self.resources.read(
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

    def publish(self, run: RunRecord) -> None:
        if run.environment != "test":
            raise ServiceError(
                "PUBLICATION_NOT_READY",
                "Production publication requires real module and player-path acceptance",
            )
        if self.resources is None:
            raise ServiceError(
                "MODULE_NOT_CONFIGURED", "Resource reader is required for publication"
            )
        self.verify_sources(run)
        package = self.load(run, "runtime", RuntimePackage)
        PackageBundle(
            environment=run.environment,
            distribution_scope="internal_preview",
            route=self.load(run, "route", RouteRecord),
            route_ref=self.reference(run, "route"),
            evidence=self.load(run, "evidence", EvidencePackage),
            evidence_ref=self.reference(run, "evidence"),
            narrative=self.load(run, "draft", NarrativeDraft).package,
            narrative_ref=self.reference(run, "narrative"),
            runtime=package,
            runtime_ref=self.reference(run, "runtime"),
            reviews=self.snapshot(run, ("evidence", "narrative", "publication")),
        )
        publication = PublicationService(
            self.database, self.releases, self.resources, self.package_loader
        )
        reviews = self.snapshot(run, ("evidence", "narrative", "publication"))
        release = publication.stage(
            run, package, tuple(decision.decision_id for decision in reviews.decisions)
        )
        # Files may take time to write. Re-read business state and approvals before pointer CAS.
        current = self.database.run(run.state.run_id)
        if current.state.revision != run.state.revision:
            raise ServiceError("STATE_STALE", "Run changed during release preparation")
        self.snapshot(current, ("evidence", "narrative", "publication"))
        self.verify_sources(current)
        self.activity.check()
        self.database.commit_release(current, release)

    def current_release(self, project_id: str) -> ReleaseRecord | None:
        release_id = self.database.current_release(project_id)
        if release_id is None:
            return None
        release = self.database.release(release_id)
        try:
            run = self.database.run(release.manifest.run_id)
            if (
                release.status != "published"
                or run.state.status != "published"
                or run.current_release_id != release_id
                or run.state.runtime_ref != release.manifest.runtime_ref
            ):
                raise ServiceError(
                    "RELEASE_STALE", "Current release does not match its committed run"
                )
            self.validate_run(run)
            self.verify_sources(run)
            self.snapshot(run, ("evidence", "narrative", "publication"))
            PublicationService.verify(
                self.releases / project_id / release_id, release, self.package_loader
            )
        except (ServiceError, ValidationError, OSError) as error:
            code = error.code if isinstance(error, ServiceError) else "RELEASE_REVALIDATION_FAILED"
            self.database.retire_release(release_id, code)
            return None
        return release

    def reconcile_releases(self) -> None:
        for release in self.database.current_releases():
            self.current_release(release.manifest.project_id)

    def validate_run(self, run: RunRecord) -> None:
        policy = (
            self.execution.policy
            if self.execution is not None
            else LocalExecutionPolicy(environment=self.environment)
        )
        if (
            run.environment != self.environment
            or run.state.graph_version != policy.graph_version
            or run.state.policy_ref.sha256 != CanonicalSerializer.digest(policy)
        ):
            raise ServiceError(
                "RUN_VERSION_UNSUPPORTED",
                "Run graph, policy or environment requires an explicit migration",
            )

    def fail(self, run_id: str, error: Exception) -> None:
        run = self.database.run(run_id)
        if run.state.status in ("cancelled", "published", "no_feasible_story"):
            return
        code = error.code if isinstance(error, ServiceError) else "STAGE_FAILED"
        message = (
            str(error)
            if isinstance(error, ServiceError)
            else "Stage failed validation or I/O; inspect the configured adapter"
        )
        status = (
            "budget_exhausted"
            if code == "BUDGET_EXHAUSTED"
            else "blocked"
            if code
            in (
                "MODULE_NOT_CONFIGURED",
                "MODULE_BLOCKED",
                "CAPABILITY_UNSUPPORTED",
                "EVIDENCE_GAP",
                "RUN_VERSION_UNSUPPORTED",
                "MODEL_UNAVAILABLE",
                "MODEL_NOT_ALLOWED",
                "TOOL_NOT_ALLOWED",
                "TOOL_UNAVAILABLE",
                "MODEL_CONTEXT_LIMIT",
                "SKILL_CHANGED",
                "PROVIDER_AUTHENTICATION_FAILED",
                "PROVIDER_FORBIDDEN",
                "PROVIDER_RATE_LIMITED",
                "PROVIDER_REQUEST_REJECTED",
            )
            else "failed"
        )
        if code in (
            "OUTCOME_UNKNOWN",
            "REVIEW_REVOKED",
            "APPROVAL_AUTHORITY_LOST",
            "REVIEW_STALE",
            "ATTEMPT_LIMIT",
            "EXECUTION_INPUT_CHANGED",
            "EXECUTION_RESULT_CHANGED",
            "LEDGER_INCONSISTENT",
            "LEDGER_MISSING",
            "OPERATION_ABANDONED",
            "RESEARCH_NO_PROGRESS",
            "RESEARCH_OPERATION_LIMIT",
        ):
            status = "needs_review"
        problem = WorkflowError(
            code=code,
            message=message,
            retryable=status in ("blocked", "failed"),
            owner="workflow",
            field_path="",
        )
        self.database.save(
            updated(
                run,
                state=updated(
                    run.state, revision=run.state.revision + 1, status=status, last_error=problem
                ),
            ),
            run.state.revision,
            code,
        )
        logger.error(
            "stage_failed",
            extra={
                "run_id": run_id,
                "project_id": run.state.project_id,
                "stage": run.state.node,
                "status": status,
                "error_code": code,
                "error_type": type(error).__name__,
            },
        )
