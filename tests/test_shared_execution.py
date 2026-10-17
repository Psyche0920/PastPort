"""Shared calls use real HTTP/SQLite/graph boundaries with explicit fake provider receipts."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from test_service import (
    FIXTURES,
    approve_gate,
    confirm_direction,
    headers,
    project_body,
    settings,
    wait_for,
)
from test_workflow_branches import stopped

from pastport.adapters.content import (
    LocalContentFiles,
    LocalEvidenceAdapter,
    LocalNarrativeAdapter,
    project_payload,
)
from pastport.adapters.database import EditorialDatabase
from pastport.adapters.model_provider import FakeModelProvider
from pastport.api.app import create_app
from pastport.application.execution_models import (
    ExecutionBinding,
    ExecutionSettings,
    ModelPolicy,
    ProviderRegistration,
    ProviderRequest,
    ProviderResponse,
)
from pastport.application.updates import updated
from pastport.application.workflow_control import SkillResultMapper
from pastport.domain.common import ArtifactRef
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    EvidenceFindings,
    ModuleResult,
    ResearchRequest,
)
from pastport.domain.workflow import SkillResult, ToolRequest
from pastport.ports.execution import ModuleServices
from pastport.ports.modules import ExecutionContext, ModelRequest

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def execution(
    role: Literal["research", "story"] = "story", *, tools: bool = False
) -> ExecutionSettings:
    return ExecutionSettings(
        models=(
            ModelPolicy(
                role=role,
                provider="fake",
                model="fixture-model-1",
                price_version="test-price-1",
                input_microusd_per_million=1000000,
                output_microusd_per_million=2000000,
                maximum_input_tokens=128000,
                maximum_output_tokens=10000,
            ),
        ),
        allowed_tools=("read_source", "lookup_local") if tools else (),
    )


def start(client: TestClient, *, input_budget: int = 2000000) -> str:
    response = client.post("/api/v1/projects", headers=headers(), json=project_body("project-1"))
    assert response.status_code == 201, response.text
    budget = json.loads((FIXTURES / "budget-policy.json").read_bytes())
    budget.update(
        max_model_requests=20,
        max_input_tokens=input_budget,
        max_output_tokens=200000,
        max_fetch_requests=10,
        max_search_requests=4,
        max_cost_microusd=10000000,
    )
    response = client.post(
        "/api/v1/projects/project-1/runs",
        headers=headers(),
        json=dict(
            budget_policy=budget,
            policy_ref=client.get("/api/v1/projects/project-1/policy", headers=headers()).json(),
        ),
    )
    assert response.status_code == 202, response.text
    return str(response.json()["state"]["run_id"])


class ProviderTape:
    def __init__(
        self,
        mode: Literal["valid", "invalid", "unknown", "error", "research", "no_progress"] = "valid",
    ) -> None:
        self.mode = mode
        self.calls: list[ProviderRequest] = []

    def respond(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        envelope = json.loads(request.input_text)
        project = envelope["project_id"]
        if envelope["mode"] == "discover":
            result = json.loads((FIXTURES / "discover-result.json").read_bytes())["payload"]
            result = project_payload(result, project)
            assert isinstance(result, dict)
            candidates = result["candidates"]
            assert isinstance(candidates, list)
            for candidate in candidates:
                assert isinstance(candidate, dict)
                candidate["source_refs"] = envelope["input_refs"]
        else:
            result = json.loads((FIXTURES / "research-result.json").read_bytes())["payload"]
            result = project_payload(result, project)
            assert isinstance(result, dict)
            question = envelope["parent_request"]["evidence_request"]
            result["request_id"] = question["request_id"]
            routes = result["route_candidates"]
            assert isinstance(routes, list)
            for route in routes:
                assert isinstance(route, dict)
                route["candidate_id"] = question["candidate_id"]
            tool = None
            decision = "complete"
            if self.mode == "no_progress" or len(self.calls) == 1:
                decision = "request_tool"
                tool = dict(
                    kind="lookup_local" if self.mode == "no_progress" else "read_source",
                    question_id=question["request_id"],
                    query="no-match-" + str(len(self.calls))
                    if self.mode == "no_progress"
                    else None,
                    source_id=None
                    if self.mode == "no_progress"
                    else envelope["parent_request"]["index"]["sources"][0]["source_id"],
                    site_ids=[envelope["parent_request"]["index"]["sites"][0]["site_id"]],
                    limit=1,
                )
            result = dict(
                request_id=envelope["request_id"],
                skill="evidence-review",
                mode="research",
                input_refs=envelope["input_refs"],
                decision=decision,
                reason_code="TEST_RESEARCH",
                reason="Inspect registered evidence",
                payload=result if decision == "complete" else None,
                issues=[],
                changed_ids=[],
                evidence_requests=[],
                tool_request=tool,
            )
        return ProviderResponse(
            raw_json='{"transport":"explicit-fake"}',
            output_text=json.dumps({} if self.mode == "invalid" else result),
            provider_request_id="fake-receipt-" + str(len(self.calls)),
            input_tokens=None if self.mode == "unknown" else 100,
            output_tokens=None if self.mode == "unknown" else 20,
            error_code="PROVIDER_AUTHENTICATION_FAILED" if self.mode == "error" else None,
        )

    def registration(self) -> tuple[ProviderRegistration, ...]:
        return (ProviderRegistration("fake", FakeModelProvider(self.respond)),)


class GatewayNarrative(LocalNarrativeAdapter):
    def __init__(
        self,
        services: ModuleServices,
        *,
        twice: bool = False,
        forge: bool = False,
        forbidden_tool: bool = False,
    ) -> None:
        super().__init__(LocalContentFiles(FIXTURES, allow_synthetic=True))
        self.services, self.twice, self.forge, self.forbidden_tool = (
            services,
            twice,
            forge,
            forbidden_tool,
        )

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        if self.forge:
            context = ExecutionContext(
                updated(context.metadata, allowed_tools=("search_web",)), context.cancellation
            )
        if self.forbidden_tool:
            await self.services.tools.execute(
                ToolRequest(
                    kind="lookup_local",
                    question_id="invented",
                    query="source",
                    source_id=None,
                    site_ids=(),
                    limit=1,
                ),
                context,
            )
        assert context.metadata.skill_ref is not None
        index = next(r for r in context.metadata.input_refs if r.kind == "source_index")
        call = ModelRequest(
            role="story",
            input_refs=(index,),
            skill_ref=context.metadata.skill_ref,
            output_model=CandidateSetDraft,
        )
        first = await self.services.models.generate(call, context)
        if self.twice:
            second = await self.services.models.generate(call, context)
            assert first == second
        return ModuleResult[CandidateSetDraft](
            outcome="completed",
            payload=first.payload,
            issues=(),
            evidence_requests=(),
            changed_ids=(),
            reason="Fake provider interface result",
        )


class GatewayEvidence(LocalEvidenceAdapter):
    def __init__(self, services: ModuleServices) -> None:
        super().__init__(LocalContentFiles(FIXTURES, allow_synthetic=True))
        self.services = services

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        assert context.metadata.skill_ref is not None
        index = next(r for r in context.metadata.input_refs if r.kind == "source_index")
        result = await self.services.research.run(
            ModelRequest(
                role="research",
                input_refs=(index,),
                skill_ref=context.metadata.skill_ref,
                output_model=SkillResult[EvidenceFindings],
            ),
            context,
        )
        return SkillResultMapper.to_module_result(result, ModuleResult[EvidenceFindings])


def test_shared_model_call_is_charged_once_and_parent_time_is_not_counted_twice(
    tmp_path: Path,
) -> None:
    tape = ProviderTape()
    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(
            config,
            providers=tape.registration(),
            narrative_factory=lambda s: GatewayNarrative(s, twice=True),
        )
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        wait_for(client, run_id, "published")
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert len(tape.calls) == 1 and budget["used"]["model_requests"] == 1
        assert budget["used"]["input_tokens"] == 100 and budget["used"]["output_tokens"] == 20
        assert budget["used"]["cost_microusd"] == 140
        child = [e for e in budget["entries"] if ":model:" in e["operation_id"]]
        assert len(child) == 1 and child[0]["settlement"]["actual"]["active_milliseconds"] == 0
        assert not any(budget["held"].values())
        assert "untrusted data" in tape.calls[0].instructions
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.provider_request(child[0]["operation_id"]) == tape.calls[0]
        run = database.run(run_id)
        binding_artifact = next(
            a for a in run.artifacts if a.reference.artifact_id == run_id + ":execution-binding"
        )
        binding = ExecutionBinding.model_validate_json(binding_artifact.payload_json)
        assert binding.settings == config.execution
        assert binding.skills[0].files[0].text and binding.skills[0].files[0].sha256


@pytest.mark.parametrize("kind", ["budget", "forged", "tool"])
def test_refused_calls_never_dispatch_to_provider(tmp_path: Path, kind: str) -> None:
    tape = ProviderTape()
    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(
            config,
            providers=tape.registration(),
            narrative_factory=lambda s: GatewayNarrative(
                s, forge=kind == "forged", forbidden_tool=kind == "tool"
            ),
        )
    ) as client:
        run_id = start(client, input_budget=1 if kind == "budget" else 2000000)
        result = stopped(
            client,
            run_id,
            "budget_exhausted" if kind == "budget" else "failed" if kind == "forged" else "blocked",
        )
        assert not tape.calls
        assert result.state.last_error is not None
        assert (
            result.state.last_error.code
            == {
                "budget": "BUDGET_EXHAUSTED",
                "forged": "EXECUTION_NOT_AUTHORIZED",
                "tool": "TOOL_NOT_ALLOWED",
            }[kind]
        )


@pytest.mark.parametrize("mode", ["invalid", "unknown", "error"])
def test_failure_receipts_preserve_known_or_unknown_usage(
    tmp_path: Path, mode: Literal["invalid", "unknown", "error"]
) -> None:
    tape = ProviderTape(mode)
    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        run = stopped(
            client,
            run_id,
            "failed" if mode == "invalid" else "needs_review" if mode == "unknown" else "blocked",
        )
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        child = next(e for e in budget["entries"] if ":model:" in e["operation_id"])
        assert len(tape.calls) == 1
        receipt = EditorialDatabase(tmp_path / "editorial.sqlite3").execution_receipt(
            child["operation_id"]
        )
        assert receipt is not None and receipt.response is not None and receipt.response.raw_json
        if mode == "unknown":
            assert child["state"] == "unknown" and child["settlement"] is None
            assert budget["held"]["model_requests"] == 1
        else:
            assert child["state"] == "settled" and budget["used"]["model_requests"] == 1
            if mode == "invalid":
                resumed = client.post(
                    "/api/v1/runs/" + run_id + "/resume",
                    headers=headers(),
                    json=dict(
                        expected_revision=run.state.revision,
                        reason="Replay recorded invalid response",
                    ),
                )
                assert resumed.status_code == 202
                stopped(client, run_id, "failed")
                assert len(tape.calls) == 1


def test_research_role_reads_registered_source_then_finishes_through_human_gates(
    tmp_path: Path,
) -> None:
    tape = ProviderTape("research")
    config = replace(
        settings(tmp_path), execution=execution("research", tools=True), skill_directory=SKILLS
    )
    with TestClient(
        create_app(config, providers=tape.registration(), evidence_factory=GatewayEvidence)
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        ready = wait_for(client, run_id, "waiting_review")
        assert ready.state.node == "evidence_review" and len(tape.calls) == 2
        assert "utf8-offset-" in tape.calls[1].input_text
        assert "synthetic" in tape.calls[1].input_text.lower()
        for _ in range(3):
            approve_gate(client, run_id)
        wait_for(client, run_id, "published")
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert budget["used"]["model_requests"] == 2 and budget["used"]["fetch_requests"] == 1


def test_two_empty_research_steps_stop_without_spinning_or_resetting_rounds(tmp_path: Path) -> None:
    tape = ProviderTape("no_progress")
    config = replace(
        settings(tmp_path), execution=execution("research", tools=True), skill_directory=SKILLS
    )
    with TestClient(
        create_app(config, providers=tape.registration(), evidence_factory=GatewayEvidence)
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        run = stopped(client, run_id, "needs_review")
        assert (
            run.state.last_error is not None and run.state.last_error.code == "RESEARCH_NO_PROGRESS"
        )
        assert len(tape.calls) == 2 and run.state.research_rounds_started == 1


def test_fake_provider_cannot_be_enabled_in_production(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Fake model"):
        create_app(
            replace(
                settings(tmp_path, test_mode=False), execution=execution(), skill_directory=SKILLS
            )
        )


def test_saved_response_and_usage_receipt_recover_without_repeating_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pastport.application.reliability import UsageSettlement

    tape = ProviderTape()
    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    original = EditorialDatabase.finish_operation
    interrupted = False

    def finish(
        self: EditorialDatabase,
        operation_id: str,
        result_json: str,
        active_milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        nonlocal interrupted
        if ":model:" in operation_id and not interrupted:
            interrupted = True
            raise RuntimeError("Crash after raw response receipt, before usage settlement")
        original(self, operation_id, result_json, active_milliseconds, settlement)

    monkeypatch.setattr(EditorialDatabase, "finish_operation", finish)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        run = stopped(client, run_id, "failed")
        assert interrupted and len(tape.calls) == 1
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(
                expected_revision=run.state.revision, reason="Recover known response and usage"
            ),
        )
        assert response.status_code == 202
        wait_for(client, run_id, "needs_review")
        assert len(tape.calls) == 1
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert budget["used"]["model_requests"] == 1 and not any(budget["held"].values())


def test_skill_change_is_refused_before_dispatch(tmp_path: Path) -> None:
    import shutil

    skill_root = tmp_path / "skills"
    shutil.copytree(SKILLS, skill_root)
    tape = ProviderTape()
    config = replace(settings(tmp_path / "data"), execution=execution(), skill_directory=skill_root)

    class ChangedSkill(GatewayNarrative):
        async def discover(
            self, request: DiscoverRequest, context: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            entry = skill_root / "narrative/SKILL.md"
            entry.write_text(entry.read_text() + "\nChanged after policy pin.\n")
            return await super().discover(request, context)

    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=ChangedSkill)
    ) as client:
        run_id = start(client)
        run = stopped(client, run_id, "blocked")
        assert (
            not tape.calls
            and run.state.last_error is not None
            and run.state.last_error.code == "SKILL_CHANGED"
        )


def test_receipt_inspection_is_project_authorized_and_hides_provider_payloads(
    tmp_path: Path,
) -> None:
    from test_service import RESTRICTED_TOKEN

    tape = ProviderTape("research")
    config = replace(
        settings(tmp_path), execution=execution("research", tools=True), skill_directory=SKILLS
    )
    with TestClient(
        create_app(config, providers=tape.registration(), evidence_factory=GatewayEvidence)
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        wait_for(client, run_id, "waiting_review")
        denied = client.get(
            "/api/v1/runs/" + run_id + "/executions", headers=headers(token=RESTRICTED_TOKEN)
        )
        assert denied.status_code == 403
        response = client.get("/api/v1/runs/" + run_id + "/executions", headers=headers())
        assert (
            response.status_code == 200
            and "raw_json" not in response.text
            and "instructions" not in response.text
        )
        refs = [
            item["artifact_ref"]
            for item in response.json()
            if item["artifact_ref"] and ":fetch:" in item["operation_id"]
        ]
        assert len(refs) == 1
        artifact = client.get("/api/v1/artifacts/" + refs[0]["artifact_id"], headers=headers())
        assert artifact.status_code == 200 and artifact.json()["payload"]["status"] == "read"
        denied_artifact = client.get(
            "/api/v1/artifacts/" + refs[0]["artifact_id"], headers=headers(token=RESTRICTED_TOKEN)
        )
        assert denied_artifact.status_code == 403


@pytest.mark.parametrize("kind", ["project", "skill", "schema"])
def test_model_cannot_change_project_skill_or_output_boundary(tmp_path: Path, kind: str) -> None:
    from pastport.domain.common import ReviewDecision

    tape = ProviderTape()
    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)

    class UnpermittedModel(GatewayNarrative):
        async def discover(
            self, request: DiscoverRequest, context: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            assert context.metadata.skill_ref is not None
            ref = next(r for r in context.metadata.input_refs if r.kind == "source_index")
            skill = context.metadata.skill_ref
            if kind == "project":
                ref = updated(ref, project_id="other-project")
            if kind == "skill":
                skill = updated(skill, sha256="0" * 64)
            if kind == "schema":
                await self.services.models.generate(
                    ModelRequest(
                        role="story",
                        input_refs=(ref,),
                        skill_ref=skill,
                        output_model=ReviewDecision,
                    ),
                    context,
                )
            else:
                await self.services.models.generate(
                    ModelRequest(
                        role="story",
                        input_refs=(ref,),
                        skill_ref=skill,
                        output_model=CandidateSetDraft,
                    ),
                    context,
                )
            raise AssertionError("Expected refusal")

    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=UnpermittedModel)
    ) as client:
        run_id = start(client)
        run = stopped(client, run_id, "blocked" if kind == "skill" else "failed")
        assert not tape.calls and run.state.last_error is not None
        assert (
            run.state.last_error.code
            == {
                "project": "PROJECT_MISMATCH",
                "skill": "MODEL_NOT_ALLOWED",
                "schema": "OUTPUT_SCHEMA_NOT_ALLOWED",
            }[kind]
        )


def test_cancellation_after_dispatch_keeps_known_usage_and_stores_no_candidate(
    tmp_path: Path,
) -> None:
    import asyncio
    import threading
    import time

    from test_workflow_branches import record

    tape = ProviderTape()
    started, release = threading.Event(), threading.Event()

    class SlowProvider:
        async def respond(
            self, request: ProviderRequest, timeout_seconds: float
        ) -> ProviderResponse:
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            return tape.respond(request)

    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(
            config,
            providers=(ProviderRegistration("fake", SlowProvider()),),
            narrative_factory=GatewayNarrative,
        )
    ) as client:
        run_id = start(client)
        try:
            assert started.wait(5)
            run = record(client, run_id)
            cancelled = client.post(
                "/api/v1/runs/" + run_id + "/cancel",
                headers=headers(),
                json=dict(
                    expected_revision=run.state.revision,
                    reason="Cancel the in-flight model operation",
                ),
            )
            assert cancelled.status_code == 202
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
            if budget["used"]["model_requests"] == 1 and not any(budget["held"].values()):
                break
            time.sleep(0.02)
        assert budget["used"]["model_requests"] == 1 and not any(budget["held"].values())
        run = record(client, run_id)
        assert run.state.status == "cancelled" and not any(
            a.reference.kind == "candidate_set" for a in run.artifacts
        )


def test_changing_inputs_cannot_bypass_stage_model_call_limit(tmp_path: Path) -> None:
    tape = ProviderTape()

    class TooManyCalls(GatewayNarrative):
        async def discover(
            self, request: DiscoverRequest, context: ExecutionContext
        ) -> ModuleResult[CandidateSetDraft]:
            assert context.metadata.skill_ref is not None
            index = next(r for r in context.metadata.input_refs if r.kind == "source_index")
            manifest = next(r for r in context.metadata.input_refs if r.kind == "source_manifest")
            for refs in ((index,), (manifest,), (index, manifest)):
                await self.services.models.generate(
                    ModelRequest(
                        role="story",
                        input_refs=refs,
                        skill_ref=context.metadata.skill_ref,
                        output_model=CandidateSetDraft,
                    ),
                    context,
                )
            raise AssertionError("Expected a bounded-operation refusal")

    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=TooManyCalls)
    ) as client:
        run_id = start(client)
        run = stopped(client, run_id, "needs_review")
        assert len(tape.calls) == 2 and run.state.last_error is not None
        assert run.state.last_error.code == "RESEARCH_OPERATION_LIMIT"


def test_actual_usage_over_a_single_reservation_is_kept_and_blocks_further_work(
    tmp_path: Path,
) -> None:
    tape = ProviderTape()

    def oversized(request: ProviderRequest) -> ProviderResponse:
        return updated(tape.respond(request), output_tokens=10001)

    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(
            config,
            providers=(ProviderRegistration("fake", FakeModelProvider(oversized)),),
            narrative_factory=GatewayNarrative,
        )
    ) as client:
        run_id = start(client)
        run = stopped(client, run_id, "budget_exhausted")
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert len(tape.calls) == 1 and budget["used"]["output_tokens"] == 10001
        assert run.state.last_error is not None and run.state.last_error.code == "BUDGET_EXHAUSTED"


@pytest.mark.parametrize(
    "content,status", [(b"", "inaccessible"), (b"%PDF-no-parser", "needs_ocr"), (b"\xff", "failed")]
)
def test_registered_source_read_statuses_and_cache_are_explicit(
    tmp_path: Path, content: bytes, status: str
) -> None:
    import hashlib

    from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
    from pastport.domain.modules import IndexRequest, InventoryRequest
    from pastport.domain.resources import ResourceData, ResourceReference

    digest = hashlib.sha256(content).hexdigest()

    class Resource:
        reads = 0

        def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
            self.reads += 1
            return ResourceData(reference, content, "application/octet-stream")

    resource = Resource()
    observed = []

    class InspectSource(GatewayEvidence):
        async def inventory(
            self, request: InventoryRequest, context: ExecutionContext
        ) -> ModuleResult[SourceManifestDraft]:
            result = await super().inventory(request, context)
            assert result.payload is not None
            return updated(
                result,
                payload=updated(
                    result.payload,
                    sources=tuple(updated(s, file_sha256=digest) for s in result.payload.sources),
                ),
            )

        async def index(
            self, request: IndexRequest, context: ExecutionContext
        ) -> ModuleResult[SourceIndexDraft]:
            result = await super().index(request, context)
            assert result.payload is not None
            return updated(
                result,
                payload=updated(
                    result.payload,
                    sources=tuple(updated(s, file_sha256=digest) for s in result.payload.sources),
                ),
            )

        async def research(
            self, request: ResearchRequest, context: ExecutionContext
        ) -> ModuleResult[EvidenceFindings]:
            source = request.index.sources[0]
            reference = ArtifactRef(
                artifact_id=source.source_id,
                project_id=context.metadata.project_id,
                kind="source",
                schema_version="0.1.0",
                content_version=source.version,
                sha256=source.file_sha256,
            )
            first = await self.services.sources.read(reference, context)
            assert first == await self.services.sources.read(reference, context)
            observed.append(first.status)
            tool = await self.services.tools.execute(
                ToolRequest(
                    kind="read_source",
                    question_id=request.evidence_request.request_id,
                    query=None,
                    source_id=source.source_id,
                    site_ids=(request.index.sites[0].site_id,),
                    limit=1,
                ),
                context,
            )
            assert tool.status == ("needs_ocr" if status == "needs_ocr" else "inaccessible")
            return ModuleResult[EvidenceFindings](
                outcome="blocked",
                payload=None,
                issues=(),
                changed_ids=(),
                evidence_requests=(),
                reason="Status probe complete",
            )

    config = replace(
        settings(tmp_path),
        execution=ExecutionSettings(allowed_tools=("read_source",)),
        skill_directory=SKILLS,
    )
    with TestClient(
        create_app(config, resources=resource, evidence_factory=InspectSource)
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        stopped(client, run_id, "blocked")
        assert observed == [status] and resource.reads == 1
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert budget["used"]["fetch_requests"] == 1


def test_configured_openai_adapter_reaches_shared_ledger_without_network(tmp_path: Path) -> None:
    import httpx

    from pastport.adapters.model_provider import OpenAIResponsesProvider

    tape = ProviderTape()
    base = execution()
    config = replace(
        settings(tmp_path),
        execution=updated(base, models=(updated(base.models[0], provider="openai"),)),
        skill_directory=SKILLS,
    )

    def handler(wire: httpx.Request) -> httpx.Response:
        body = json.loads(wire.content)
        envelope = json.loads(body["input"])
        assert envelope["project_id"] == "project-1"
        payload = json.loads((FIXTURES / "discover-result.json").read_bytes())["payload"]
        payload = project_payload(payload, "project-1")
        assert isinstance(payload, dict) and isinstance(payload["candidates"], list)
        for candidate in payload["candidates"]:
            assert isinstance(candidate, dict)
            candidate["source_refs"] = envelope["input_refs"]
        return httpx.Response(
            200,
            headers={"x-request-id": "http-mock-request-1"},
            json=dict(
                id="resp-test",
                model=body["model"],
                status="completed",
                output=[
                    dict(
                        type="message", content=[dict(type="output_text", text=json.dumps(payload))]
                    )
                ],
                usage=dict(input_tokens=100, output_tokens=20),
            ),
        )

    provider = OpenAIResponsesProvider("not-a-real-key", transport=httpx.MockTransport(handler))
    with TestClient(
        create_app(
            config,
            providers=(ProviderRegistration("openai", provider),),
            narrative_factory=GatewayNarrative,
        )
    ) as client:
        run_id = start(client)
        run = wait_for(client, run_id, "needs_review")
        assert any(a.reference.kind == "candidate_set" for a in run.artifacts)
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        entry = next(e for e in budget["entries"] if ":model:" in e["operation_id"])
        assert entry["settlement"]["source"] == "provider"
        assert entry["settlement"]["provider_request_id"] == "http-mock-request-1"
        assert budget["used"]["cost_microusd"] == 140
        stored = EditorialDatabase(tmp_path / "editorial.sqlite3").provider_request(
            entry["operation_id"]
        )
        assert stored is not None and "not-a-real-key" not in stored.model_dump_json()
    assert not tape.calls


@pytest.mark.parametrize("boundary", ["fetch", "tool"])
def test_saved_source_or_tool_receipt_recovers_without_reading_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    from pastport.adapters.resources import LocalResourceReader
    from pastport.application.reliability import UsageSettlement
    from pastport.domain.resources import ResourceData, ResourceReference

    class CountingReader(LocalResourceReader):
        calls = 0

        def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
            if reference.kind == "source":
                self.calls += 1
            return super().read(reference, maximum_bytes)

    resources = CountingReader(FIXTURES, fixture_projects=True)
    tape = ProviderTape("research")
    config = replace(
        settings(tmp_path), execution=execution("research", tools=True), skill_directory=SKILLS
    )
    original = EditorialDatabase.finish_operation
    interrupted = False

    def finish(
        self: EditorialDatabase,
        operation_id: str,
        result_json: str,
        active_milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        nonlocal interrupted
        if ":" + boundary + ":" in operation_id and not interrupted:
            interrupted = True
            raise RuntimeError("Crash after durable tool/source receipt")
        original(self, operation_id, result_json, active_milliseconds, settlement)

    monkeypatch.setattr(EditorialDatabase, "finish_operation", finish)
    with TestClient(
        create_app(
            config,
            providers=tape.registration(),
            evidence_factory=GatewayEvidence,
            resources=resources,
        )
    ) as client:
        run_id = start(client)
        confirm_direction(client, run_id)
        run = stopped(client, run_id, "failed")
        reads = resources.calls
        assert interrupted and reads > 0 and len(tape.calls) == 1
    with TestClient(
        create_app(
            config,
            providers=tape.registration(),
            evidence_factory=GatewayEvidence,
            resources=resources,
        )
    ) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(
                expected_revision=run.state.revision, reason="Recover known source/tool receipt"
            ),
        )
        assert response.status_code == 202
        wait_for(client, run_id, "waiting_review")
        assert resources.calls == reads and len(tape.calls) == 2
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert budget["used"]["fetch_requests"] == 1 and not any(budget["held"].values())


@pytest.mark.parametrize(
    "relative",
    [
        "../outside.md",
        "references/../../outside.md",
        "/tmp/outside.md",
        "references/%2e%2e/outside.md",
    ],
)
def test_skill_reference_cannot_escape_approved_directory(tmp_path: Path, relative: str) -> None:
    from pastport.adapters.skills import SkillLoader
    from pastport.application.models import ServiceError

    policy = updated(execution().models[0], references=(relative,))
    with pytest.raises(ServiceError) as failure:
        SkillLoader(SKILLS).load(policy)
    assert failure.value.code == "SKILL_PATH_INVALID"


def test_skill_reference_hash_tracks_only_explicit_approved_files(tmp_path: Path) -> None:
    import shutil

    from pastport.adapters.skills import SkillLoader
    from pastport.application.models import ServiceError

    shutil.copytree(SKILLS, tmp_path / "skills")
    root = tmp_path / "skills"
    folder = root / "narrative/references"
    folder.mkdir(exist_ok=True)
    approved = folder / "approved.md"
    ignored = folder / "not-approved.md"
    approved.write_text("Approved professional guidance.")
    ignored.write_text("Unselected reference.")
    policy = updated(execution().models[0], references=("references/approved.md",))
    loader = SkillLoader(root)
    first = loader.load(policy)
    assert len(first.files) == 2
    ignored.write_text("This must not alter the binding.")
    assert loader.load(policy) == first
    approved.write_text("Changed approved guidance.")
    assert loader.load(policy) != first
    approved.unlink()
    approved.symlink_to(ignored)
    with pytest.raises(ServiceError) as failure:
        loader.load(policy)
    assert failure.value.code == "SKILL_PATH_INVALID"
