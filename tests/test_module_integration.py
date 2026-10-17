"""Replace either module and resource storage without modifying workflow internals."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_service import approve_gate, confirm_direction, create_run, headers, settings, wait_for

from pastport.adapters.content import LocalContentFiles
from pastport.api.app import create_app
from pastport.application.updates import updated
from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ResearchRequest,
    ReviseRequest,
)
from pastport.domain.resources import ResourceData, ResourceReference
from pastport.ports.modules import ExecutionContext

FIXTURES = Path(__file__).parent / "fixtures/reference"


class IndependentEvidence:
    """A separate port implementation; the workflow never imports or inspects it."""

    def __init__(self, directory: Path) -> None:
        self.files = LocalContentFiles(directory, allow_synthetic=True)
        self.calls: list[str] = []

    def __bool__(self) -> bool:
        return False  # Explicit injection must not be replaced due to truthiness.

    async def inventory(
        self, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        context.cancellation.raise_if_cancelled()
        self.calls.append("inventory")
        result = self.files.read(
            "inventory-result.json", ModuleResult[SourceManifestDraft], context.metadata.project_id
        )
        assert result.payload is not None
        return updated(
            result, payload=updated(result.payload, source_folder_id=request.folder.folder_id)
        )

    async def index(
        self, request: IndexRequest, context: ExecutionContext
    ) -> ModuleResult[SourceIndexDraft]:
        context.cancellation.raise_if_cancelled()
        self.calls.append("index")
        return self.files.read(
            "index-result.json", ModuleResult[SourceIndexDraft], context.metadata.project_id
        )

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        context.cancellation.raise_if_cancelled()
        self.calls.append("research")
        result = self.files.read(
            "research-result.json", ModuleResult[EvidenceFindings], context.metadata.project_id
        )
        assert result.payload is not None
        return updated(
            result,
            payload=updated(
                result.payload,
                request_id=request.evidence_request.request_id,
                route_candidates=tuple(
                    updated(route, candidate_id=request.evidence_request.candidate_id)
                    for route in result.payload.route_candidates
                ),
            ),
        )


class IndependentNarrative:
    def __init__(self, directory: Path) -> None:
        self.files = LocalContentFiles(directory, allow_synthetic=True)
        self.calls: list[str] = []

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        context.cancellation.raise_if_cancelled()
        self.calls.append("discover")
        result = self.files.read(
            "discover-result.json", ModuleResult[CandidateSetDraft], context.metadata.project_id
        )
        assert result.payload is not None
        index = next(
            reference
            for reference in context.metadata.input_refs
            if reference.kind == "source_index"
        )
        return updated(
            result,
            payload=updated(
                result.payload,
                candidates=tuple(
                    updated(candidate, source_refs=(index,))
                    for candidate in result.payload.candidates
                ),
            ),
        )

    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        context.cancellation.raise_if_cancelled()
        self.calls.append("draft")
        result = self.files.read(
            "draft-result.json", ModuleResult[NarrativeDraft], context.metadata.project_id
        )
        assert result.payload is not None
        package = updated(
            result.payload.package,
            evidence_package_hash=request.evidence.evidence_ref.sha256,
            candidate_id=request.selected_candidate.candidate_id,
            routes=(request.evidence.approved_route_ref,),
        )
        return updated(result, payload=updated(result.payload, package=package))

    async def revise(
        self, request: ReviseRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        context.cancellation.raise_if_cancelled()
        raise NotImplementedError("Not used by the current graph path")

    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]:
        context.cancellation.raise_if_cancelled()
        raise NotImplementedError("Not used by the current graph path")


class MemoryResources:
    """No directory paths or runtime template are available to the framework."""

    def __init__(self) -> None:
        evidence = json.loads((FIXTURES / "evidence.json").read_bytes())
        self.source = evidence["sources"][0]
        self.asset = evidence["assets"][0]
        self.calls: list[ResourceReference] = []

    def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
        assert reference.project_id == "project-1"
        self.calls.append(reference)
        if reference.kind == "source":
            assert reference.resource_id == self.source["source_id"]
            assert reference.sha256 == self.source["file_sha256"]
            return ResourceData(
                reference,
                (FIXTURES / "synthetic-source.txt").read_bytes(),
                "application/octet-stream",
            )
        assert reference.resource_id == self.asset["asset_id"]
        assert reference.sha256 == self.asset["derivative_sha256"]
        return ResourceData(
            reference, (FIXTURES / "synthetic-hatch.svg").read_bytes(), "image/svg+xml"
        )


@pytest.mark.parametrize(
    "replace_evidence,replace_narrative",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_four_module_combinations_without_runtime_template(
    tmp_path: Path, replace_evidence: bool, replace_narrative: bool
) -> None:
    content = tmp_path / "module-owned-content"
    shutil.copytree(FIXTURES, content)
    (content / "runtime.json").unlink()
    evidence = IndependentEvidence(content) if replace_evidence else None
    narrative = IndependentNarrative(content) if replace_narrative else None
    resources = MemoryResources()
    configuration = replace(settings(tmp_path / "data"), fixture_directory=content)
    if replace_evidence and replace_narrative:
        configuration = replace(configuration, fixture_directory=None)
    with TestClient(
        create_app(configuration, evidence=evidence, narrative=narrative, resources=resources)
    ) as client:
        modes = client.get("/api/v1/health").json()["modules"]
        assert modes["evidence"] == ("injected" if replace_evidence else "local")
        assert modes["narrative"] == ("injected" if replace_narrative else "local")
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        final = wait_for(client, run_id, "published")
        assert (
            client.get("/api/v1/projects/project-1/release", headers=headers()).status_code == 200
        )
        package = json.loads(
            next(item.payload_json for item in final.artifacts if item.reference.kind == "runtime")
        )
        assert package["media_manifest"][0]["relative_path"].startswith("media/")
        assert {reference.kind for reference in resources.calls} == {"source", "asset"}
        if evidence is not None:
            assert evidence.calls == ["inventory", "index", "research"]
        if narrative is not None:
            assert narrative.calls == ["discover", "draft"]


def test_missing_narrative_does_not_block_evidence_inventory_or_index(tmp_path: Path) -> None:
    evidence = IndependentEvidence(FIXTURES)
    configuration = replace(settings(tmp_path), fixture_directory=None, narrative_mode="disabled")
    with TestClient(create_app(configuration, evidence=evidence)) as client:
        run_id = create_run(client)
        stopped = wait_for(client, run_id, "blocked")
        assert stopped.state.node == "discover_story"
        assert evidence.calls == ["inventory", "index"]
        assert (
            stopped.state.last_error is not None
            and "Narrative adapter" in stopped.state.last_error.message
        )


def test_missing_resource_reader_does_not_block_story_drafting(tmp_path: Path) -> None:
    configuration = replace(settings(tmp_path), fixture_directory=None)
    with TestClient(
        create_app(
            configuration,
            evidence=IndependentEvidence(FIXTURES),
            narrative=IndependentNarrative(FIXTURES),
        )
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        narrative_review = wait_for(client, run_id, "waiting_review")
        assert narrative_review.state.node == "narrative_review"
        approve_gate(client, run_id)
        stopped = wait_for(client, run_id, "blocked")
        assert stopped.state.node == "assemble_package"
        assert (
            stopped.state.last_error is not None
            and "Assembly adapter" in stopped.state.last_error.message
        )


def test_explicit_selection_never_silently_falls_back(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires an injected"):
        create_app(replace(settings(tmp_path), evidence_mode="injected"))
    with pytest.raises(ValueError, match="different explicit mode"):
        create_app(
            replace(settings(tmp_path), evidence_mode="local"),
            evidence=IndependentEvidence(FIXTURES),
        )
    with pytest.raises(ValueError, match="configured directory"):
        create_app(replace(settings(tmp_path), fixture_directory=None, resources_mode="local"))


def test_injected_resource_failure_never_falls_back_to_local_files(tmp_path: Path) -> None:
    class CorruptResources(MemoryResources):
        def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
            result = super().read(reference, maximum_bytes)
            return ResourceData(
                reference,
                b"changed" if reference.kind == "asset" else result.content,
                result.media_type,
            )

    # Valid local bytes are present, but must not mask the injected backend failure.
    configuration = replace(
        settings(tmp_path),
        evidence_mode="injected",
        narrative_mode="injected",
        resources_mode="injected",
    )
    with TestClient(
        create_app(
            configuration,
            evidence=IndependentEvidence(FIXTURES),
            narrative=IndependentNarrative(FIXTURES),
            resources=CorruptResources(),
        )
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        failed = wait_for(client, run_id, "failed")
        assert failed.state.node == "assemble_package"
        assert (
            failed.state.last_error is not None and failed.state.last_error.code == "MEDIA_CHANGED"
        )
        assert failed.current_release_id is None


@pytest.mark.parametrize("invalid", ["assembly", "validation"])
def test_injected_deterministic_adapter_outputs_are_checked(tmp_path: Path, invalid: str) -> None:
    from pastport.adapters.assembly import PackageAssembler
    from pastport.domain.modules import AssemblyRequest, AssemblyResult, PackageValidationRequest
    from pastport.domain.packages import ValidationReport

    resources = MemoryResources()

    class IncorrectAssembly(PackageAssembler):
        def assemble(self, request: AssemblyRequest) -> AssemblyResult:
            result = super().assemble(request)
            from pastport.domain.common import CanonicalSerializer

            package = updated(result.package, project_id="other-project")
            return updated(
                result,
                package=package,
                report=updated(result.report, artifact_hash=CanonicalSerializer.digest(package)),
            )

    class IncorrectValidator(PackageAssembler):
        def validate(self, request: PackageValidationRequest) -> ValidationReport:
            return updated(super().validate(request), artifact_hash="0" * 64)

    configuration = replace(settings(tmp_path), fixture_directory=None)
    with TestClient(
        create_app(
            configuration,
            evidence=IndependentEvidence(FIXTURES),
            narrative=IndependentNarrative(FIXTURES),
            resources=resources,
            assembly=IncorrectAssembly(resources) if invalid == "assembly" else None,
            validator=IncorrectValidator(resources) if invalid == "validation" else None,
        )
    ) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        failed = wait_for(client, run_id, "failed")
        assert failed.state.last_error is not None
        assert failed.state.last_error.code == (
            "ASSEMBLY_OUTPUT_INVALID" if invalid == "assembly" else "VALIDATION_OUTPUT_INVALID"
        )
        assert failed.current_release_id is None
