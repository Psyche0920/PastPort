"""Preview-only assembly and sessions; no review or release mutations occur here."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pastport.application.models import Actor, RunRecord, ServiceError
from pastport.application.player_runtime import PlayerRuntimeProcess, SharedPlayerRuntime
from pastport.application.previews import (
    CreatePreview,
    PreviewActionView,
    PreviewRecord,
    PreviewRepository,
    PreviewView,
)
from pastport.application.resources import MEDIA_EXTENSIONS, RESOURCE_LIMIT, VerifiedResourceReader
from pastport.application.service import EditorialService
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract, VersionedPayload
from pastport.domain.evidence import EvidencePackage
from pastport.domain.game import ActionRequest, NarrativePackage
from pastport.domain.modules import NarrativeDraft
from pastport.domain.packages import MediaEntry, RuntimePackage
from pastport.domain.resources import ResourceData, ResourceReference
from pastport.workflow.stages import StageRunner


class PreviewService:
    def __init__(
        self,
        editorial: EditorialService,
        stages: StageRunner,
        repository: PreviewRepository,
        process: PlayerRuntimeProcess,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.editorial = editorial
        self.stages = stages
        self.repository = repository
        self.process = process
        self.clock = clock

    @staticmethod
    def current[Payload: Contract](
        run: RunRecord, suffix: str, model: type[Payload]
    ) -> tuple[ArtifactRef, Payload]:
        artifact = next(
            (
                item
                for item in reversed(run.artifacts)
                if item.reference.artifact_id == run.state.run_id + ":" + suffix
            ),
            None,
        )
        if artifact is None:
            raise ServiceError("PREVIEW_INPUT_MISSING", "Required preview content is not available")
        value = model.model_validate_json(artifact.payload_json)
        if (
            artifact.reference.project_id != run.state.project_id
            or CanonicalSerializer.digest(value) != artifact.reference.sha256
        ):
            raise ServiceError("ARTIFACT_CHANGED", "Preview input failed its identity or hash")
        versioned = value.package if isinstance(value, NarrativeDraft) else value
        if isinstance(versioned, VersionedPayload) and (
            versioned.project_id != artifact.reference.project_id
            or versioned.schema_version != artifact.reference.schema_version
            or versioned.content_version != artifact.reference.content_version
        ):
            raise ServiceError(
                "ARTIFACT_CHANGED", "Preview input version differs from its reference"
            )
        return artifact.reference, value

    def run(self, run_id: str, actor: Actor) -> RunRecord:
        run = self.editorial.run(run_id, actor)
        if run.state.status == "cancelled":
            raise ServiceError("PREVIEW_INVALIDATED", "Cancelled runs cannot be previewed")
        if run.environment != self.stages.environment:
            raise ServiceError("PREVIEW_INVALIDATED", "Preview environment differs from the run")
        return run

    def resources(self) -> VerifiedResourceReader:
        if self.stages.resources is None:
            raise ServiceError(
                "RESOURCE_UNAVAILABLE", "Preview resource reader is not configured", 503
            )
        return self.stages.resources

    def verify_evidence(self, run: RunRecord) -> tuple[ArtifactRef, EvidencePackage]:
        reference, evidence = self.current(run, "evidence", EvidencePackage)
        if evidence.project_id != run.state.project_id:
            raise ServiceError("PREVIEW_INVALIDATED", "Evidence belongs to another project")
        for source in evidence.sources:
            if run.environment != "test" and source.origin == "synthetic":
                raise ServiceError("PREVIEW_INVALIDATED", "Synthetic sources require test mode")
            self.resources().read(
                ResourceReference(
                    project_id=run.state.project_id,
                    resource_id=source.source_id,
                    kind="source",
                    version=source.version,
                    sha256=source.file_sha256,
                    source_uri=source.uri,
                ),
                RESOURCE_LIMIT,
            )
        return reference, evidence

    def media(self, evidence: EvidencePackage) -> tuple[MediaEntry, ...]:
        entries = []
        for asset in sorted(evidence.assets, key=lambda item: item.asset_id):
            if (
                asset.mapping_state != "verified"
                or asset.rights_state not in ("permitted_for_scope", "open_license")
                or "internal_preview" not in asset.allowed_uses
            ):
                raise ServiceError(
                    "ASSET_NOT_USABLE",
                    "Preview requires verified mapping and internal-preview rights",
                )
            resource = self.resources().read(
                ResourceReference(
                    project_id=evidence.project_id,
                    resource_id=asset.asset_id,
                    kind="asset",
                    version=asset.version,
                    sha256=asset.derivative_sha256,
                ),
                RESOURCE_LIMIT,
            )
            extension = MEDIA_EXTENSIONS.get(resource.media_type)
            if extension is None:
                raise ServiceError("MEDIA_TYPE_UNSUPPORTED", "Preview requires a supported image")
            entries.append(
                MediaEntry(
                    asset_id=asset.asset_id,
                    sha256=asset.derivative_sha256,
                    relative_path=f"media/{asset.asset_id}-{asset.derivative_sha256}.{extension}",
                )
            )
        return tuple(entries)

    def package(
        self, run: RunRecord, source_ref: ArtifactRef
    ) -> tuple[ArtifactRef, RuntimePackage]:
        evidence_ref, evidence = self.verify_evidence(run)
        if source_ref.artifact_id == run.state.run_id + ":draft":
            actual, draft = self.current(run, "draft", NarrativeDraft)
            narrative = draft.package
            if (
                narrative.project_id != run.state.project_id
                or narrative.evidence_package_hash != evidence_ref.sha256
                or narrative.routes != evidence.route_refs
            ):
                raise ServiceError("PREVIEW_INVALIDATED", "Draft evidence or route binding differs")
            # A projection is not an AssemblyRequest: that boundary requires human approvals.
            package = RuntimePackage(
                project_id=run.state.project_id,
                schema_version="0.1.0",
                content_version=narrative.content_version,
                package_id="preview-package-" + CanonicalSerializer.digest(draft)[:32],
                runtime_compatibility=self.stages.capabilities,
                evidence_package_hash=evidence_ref.sha256,
                narrative_package_hash=CanonicalSerializer.digest(narrative),
                game=narrative.game,
                media_manifest=self.media(evidence),
            )
        else:
            actual, package = self.current(run, "runtime", RuntimePackage)
            _, narrative = self.current(run, "narrative", NarrativePackage)
            if (
                package.evidence_package_hash != evidence_ref.sha256
                or package.narrative_package_hash != CanonicalSerializer.digest(narrative)
                or narrative.evidence_package_hash != evidence_ref.sha256
                or package.game != narrative.game
            ):
                raise ServiceError(
                    "PREVIEW_INVALIDATED", "Runtime dependencies differ from current content"
                )
            available = {item.asset_id: item.sha256 for item in self.media(evidence)}
            if any(available.get(item.asset_id) != item.sha256 for item in package.media_manifest):
                raise ServiceError("PREVIEW_INVALIDATED", "Runtime media differs from evidence")
        if source_ref != actual:
            raise ServiceError(
                "PREVIEW_INVALIDATED", "Preview source is no longer the current version"
            )
        reference = CanonicalSerializer.reference(package, "preview-runtime", "runtime")
        self.stages.package_loader.load_bytes(package.model_dump_json().encode(), reference)
        return evidence_ref, package

    def engine(self, record: PreviewRecord) -> SharedPlayerRuntime:
        return SharedPlayerRuntime(
            record.runtime_package.model_dump_json().encode(),
            record.runtime_ref,
            "preview:" + record.preview_id,
            self.stages.package_loader,
            self.process,
        )

    def validate(self, record: PreviewRecord, actor: Actor) -> None:
        if self.clock() >= record.expires_at:
            raise ServiceError("PREVIEW_EXPIRED", "Preview has expired; create a new session", 410)
        run = self.run(record.run_id, actor)
        if (
            record.actor_id != actor.actor_id
            or record.project_id != run.state.project_id
            or record.environment != run.environment
        ):
            raise ServiceError("PREVIEW_INVALIDATED", "Preview belongs to another identity")
        evidence_ref, package = self.package(run, record.source_ref)
        if (
            evidence_ref != record.evidence_ref
            or CanonicalSerializer.digest(package) != record.runtime_ref.sha256
        ):
            raise ServiceError(
                "PREVIEW_INVALIDATED", "Preview dependencies changed; create a new session"
            )

    def view(self, record: PreviewRecord) -> PreviewView:
        state = self.repository.state(record)
        self.engine(record).validate_state(record.runtime_package, state)
        return PreviewView(
            preview_id=record.preview_id,
            project_id=record.project_id,
            run_id=record.run_id,
            environment=record.environment,
            kind=record.kind,
            source_ref=record.source_ref,
            runtime_ref=record.runtime_ref,
            runtime_package=record.runtime_package,
            state=state,
            expires_at=record.expires_at,
        )

    def create(
        self, actor: Actor, run_id: str, request: CreatePreview, request_key: str
    ) -> PreviewView:
        run = self.run(run_id, actor)
        previous = self.repository.find_request(actor, run_id, request_key)
        digest = CanonicalSerializer.digest(request)
        if previous is not None:
            if previous.request_hash != digest:
                raise ServiceError(
                    "IDEMPOTENCY_CONFLICT", "Preview request key has another payload"
                )
            self.validate(previous, actor)
            return self.view(previous)
        if run.state.revision != request.expected_revision:
            raise ServiceError("STATE_STALE", "Run changed before preview creation")
        evidence_ref, package = self.package(run, request.source_ref)
        record = PreviewRecord(
            preview_id=uuid4().hex,
            actor_id=actor.actor_id,
            project_id=run.state.project_id,
            run_id=run_id,
            environment=run.environment,
            kind="test" if run.environment == "test" else "draft",
            source_ref=request.source_ref,
            evidence_ref=evidence_ref,
            runtime_ref=CanonicalSerializer.reference(package, "preview-runtime", "runtime"),
            runtime_package=package,
            expires_at=self.clock() + timedelta(hours=1),
            request_key=request_key,
            request_hash=digest,
        )
        engine = self.engine(record)
        state = engine.initial_state(package, "preview:" + record.preview_id)
        self.validate(record, actor)
        stored = self.repository.create_preview(record, state, self.clock())
        self.validate(stored, actor)
        return self.view(stored)

    def get(self, actor: Actor, run_id: str, preview_id: str) -> PreviewView:
        self.run(run_id, actor)
        record = self.repository.get(actor, run_id, preview_id)
        self.validate(record, actor)
        return self.view(record)

    def apply(
        self, actor: Actor, run_id: str, preview_id: str, action: ActionRequest
    ) -> PreviewActionView:
        self.run(run_id, actor)
        record = self.repository.get(actor, run_id, preview_id)
        for _ in range(2):
            self.validate(record, actor)
            previous = self.repository.state(record)
            result = self.engine(record).apply_action(record.runtime_package, previous, action)
            self.validate(record, actor)
            if result.state == previous or self.repository.commit(
                record, previous, result.state, self.clock()
            ):
                return PreviewActionView(preview_id=preview_id, result=result)
        raise ServiceError("STATE_STALE", "Preview changed; reload before another action")

    def asset(self, actor: Actor, run_id: str, preview_id: str, asset_id: str) -> ResourceData:
        self.run(run_id, actor)
        record = self.repository.get(actor, run_id, preview_id)
        self.validate(record, actor)
        item = next(
            (item for item in record.runtime_package.media_manifest if item.asset_id == asset_id),
            None,
        )
        if item is None:
            raise ServiceError("RESOURCE_NOT_REGISTERED", "Asset is not in this preview", 404)
        return self.resources().read(
            ResourceReference(
                project_id=record.project_id,
                resource_id=item.asset_id,
                kind="asset",
                sha256=item.sha256,
            ),
            RESOURCE_LIMIT,
        )
