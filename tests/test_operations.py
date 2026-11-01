"""F6 interventions use authenticated HTTP, durable SQLite and the real workflow worker."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_service import (
    RESTRICTED_TOKEN,
    approve_gate,
    confirm_direction,
    create_run,
    headers,
    settings,
    wait_for,
)
from test_shared_execution import SKILLS, GatewayNarrative, ProviderTape, execution, start
from test_workflow_branches import stopped

from pastport.adapters.database import EditorialDatabase
from pastport.adapters.model_provider import FakeModelProvider
from pastport.api.app import create_app
from pastport.api.settings import AppSettings
from pastport.application.activity import ActivityMeter
from pastport.application.execution_models import (
    ProviderRegistration,
    ProviderRequest,
    ProviderResponse,
)
from pastport.application.models import RunRecord, ServiceError
from pastport.application.publication import PublicationService
from pastport.application.reliability import ReleaseRecord, Usage
from pastport.application.updates import updated
from pastport.domain.packages import RuntimePackage


def operator_settings(directory: Path) -> AppSettings:
    config = settings(directory)
    admin = updated(
        config.accounts[0],
        actor=updated(
            config.accounts[0].actor, roles=(*config.accounts[0].actor.roles, "operator")
        ),
    )
    return replace(config, accounts=(admin, config.accounts[1]))


def record(client: TestClient, run_id: str) -> RunRecord:
    return RunRecord.model_validate_json(
        client.get("/api/v1/runs/" + run_id, headers=headers()).content
    )


def reconcile_body(client: TestClient, run_id: str, action: str, usage: Usage) -> dict[str, object]:
    snapshot = client.get("/api/v1/runs/" + run_id + "/interventions", headers=headers()).json()
    target = snapshot["unknown_entries"][0]
    return dict(
        expected_revision=record(client, run_id).state.revision,
        reservation_id=target["entry"]["reservation_id"],
        entry_hash=target["entry_hash"],
        action=action,
        settlement=dict(
            actual=usage.model_dump(mode="json"),
            source="operator",
            provider_request_id="fake-receipt-1" if action == "recover" else None,
        ),
        evidence=dict(
            kind="provider_receipt",
            reference="fixture-provider-record",
            description="Explicit simulated provider attestation; not a live invoice.",
        ),
        reason="Resolve the frozen reservation using the supplied receipt",
    )


def amend_body(client: TestClient, run_id: str, **limits: int) -> dict[str, object]:
    snapshot = client.get("/api/v1/runs/" + run_id + "/interventions", headers=headers()).json()
    policy = snapshot["budget_policy"]
    policy.update(limits)
    return dict(
        expected_revision=record(client, run_id).state.revision,
        budget_hash=snapshot["budget_hash"],
        budget_policy=policy,
        reason="Explicit operator authorization",
    )


def resume(client: TestClient, run_id: str) -> None:
    response = client.post(
        "/api/v1/runs/" + run_id + "/resume",
        headers=headers(),
        json=dict(
            expected_revision=record(client, run_id).state.revision,
            reason="Continue after authorized intervention",
        ),
    )
    assert response.status_code == 202, response.text


def test_operator_recovers_original_unknown_response_once_and_keeps_the_raw_receipt(
    tmp_path: Path,
) -> None:
    tape = ProviderTape("unknown")
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(
                expected_revision=record(client, run_id).state.revision,
                reason="Cannot bypass reconciliation",
            ),
        )
        assert response.status_code == 409
        body = reconcile_body(
            client,
            run_id,
            "recover",
            Usage(model_requests=1, input_tokens=100, output_tokens=20, cost_microusd=140),
        )
        same_headers = headers("same-reconciliation")
        response = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=same_headers, json=body
        )
        assert response.status_code == 200, response.text
        assert response.json()["state"]["status"] == "blocked"
        replay = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=same_headers, json=body
        )
        assert replay.json() == response.json()
        resume(client, run_id)
        wait_for(client, run_id, "needs_review")
        assert len(tape.calls) == 1
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        budget = database.budget(run_id)
        assert budget.used.model_requests == 1 and budget.used.cost_microusd == 140
        assert not any(getattr(budget.held, field) for field in Usage.model_fields)
        audit = database.interventions(run_id).reconciliations
        assert len(audit) == 1 and audit[0].original_entry.state == "unknown"
        operation_id = audit[0].original_entry.operation_id
        with database.connection() as connection:
            original = json.loads(
                connection.execute(
                    "SELECT payload_json FROM execution_receipts WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()[0]
            )
        assert original["settlement"] is None and original["response"]["input_tokens"] is None
        resolved = database.execution_receipt(operation_id)
        assert resolved is not None and resolved.settlement is not None
        assert resolved.settlement.source == "operator"
        assert audit[0].original_receipt_hash is not None


@pytest.mark.parametrize(
    "fault,code",
    [
        ("price", "PRICE_MISMATCH"),
        ("identity", "RECEIPT_MISMATCH"),
        ("source", "RECONCILIATION_SOURCE_INVALID"),
        ("hash", "RECONCILIATION_STALE"),
        ("retry", "RETRY_UNSAFE"),
        ("evidence", "RECONCILIATION_EVIDENCE_REQUIRED"),
    ],
)
def test_invalid_reconciliation_cannot_release_usage(tmp_path: Path, fault: str, code: str) -> None:
    tape = ProviderTape("unknown")
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(
            client,
            run_id,
            "recover",
            Usage(model_requests=1, input_tokens=100, output_tokens=20, cost_microusd=140),
        )
        if fault == "hash":
            body["entry_hash"] = "0" * 64
        if fault == "retry":
            body["action"] = "retry"
        settlement = body["settlement"]
        assert isinstance(settlement, dict)
        actual = settlement["actual"]
        assert isinstance(actual, dict)
        if fault == "price":
            actual["cost_microusd"] = 1
        if fault == "identity":
            settlement["provider_request_id"] = "other-receipt"
        if fault == "source":
            settlement["source"] = "provider"
        if fault == "evidence":
            evidence = body["evidence"]
            assert isinstance(evidence, dict)
            evidence["kind"] = "local_execution_record"
        response = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
        )
        assert response.status_code == 409 and response.json()["code"] == code
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.budget(run_id).held.model_requests == 1
        assert not database.interventions(run_id).reconciliations


def test_confirmed_non_execution_allows_one_retry_with_the_same_saved_request(
    tmp_path: Path,
) -> None:
    tape = ProviderTape()
    attempts: list[ProviderRequest] = []

    def provider(request: ProviderRequest) -> ProviderResponse:
        attempts.append(request)
        if len(attempts) == 1:
            raise ServiceError("OUTCOME_UNKNOWN", "Simulated transport outcome")
        return tape.respond(request)

    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(
            config,
            providers=(ProviderRegistration("fake", FakeModelProvider(provider)),),
            narrative_factory=GatewayNarrative,
        )
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(client, run_id, "retry", Usage())
        response = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
        )
        assert response.status_code == 200, response.text
        resume(client, run_id)
        wait_for(client, run_id, "needs_review")
        assert len(attempts) == 2 and attempts[0] == attempts[1]
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.budget(run_id).used.model_requests == 1
        reconciliation = database.interventions(run_id).reconciliations[0]
        assert reconciliation.command.action == "retry"
        assert reconciliation.original_receipt is not None
        assert reconciliation.original_receipt.response is None
        assert reconciliation.original_receipt.error_code == "OUTCOME_UNKNOWN"


def test_settlement_without_a_response_never_manufactures_completed_content(tmp_path: Path) -> None:
    tape = ProviderTape("unknown")
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(
            client,
            run_id,
            "settle",
            Usage(model_requests=1, input_tokens=100, output_tokens=20, cost_microusd=140),
        )
        response = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
        )
        assert response.status_code == 200
        run = record(client, run_id)
        assert run.state.status == "needs_review" and not any(
            a.reference.kind == "candidate_set" for a in run.artifacts
        )
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        operation = database.interventions(run_id).reconciliations[0].original_entry.operation_id
        with pytest.raises(ServiceError) as failure:
            database.operation_result(operation)
        assert failure.value.code == "OPERATION_ABANDONED" and len(tape.calls) == 1


def test_budget_amendment_keeps_original_policy_and_usage_then_requires_explicit_resume(
    tmp_path: Path,
) -> None:
    tape = ProviderTape()
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client, input_budget=1)
        stopped(client, run_id, "budget_exhausted")
        body = amend_body(client, run_id, max_input_tokens=2000000)
        same = headers("budget-change")
        response = client.post(
            "/api/v1/runs/" + run_id + "/budget-amendments", headers=same, json=body
        )
        assert response.status_code == 200 and not tape.calls
        assert response.json()["state"]["status"] == "blocked"
        assert (
            client.post(
                "/api/v1/runs/" + run_id + "/budget-amendments", headers=same, json=body
            ).json()
            == response.json()
        )
        resume(client, run_id)
        wait_for(client, run_id, "needs_review")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.run(run_id).budget_policy.max_input_tokens == 1
        assert database.budget_policy(run_id).max_input_tokens == 2000000
        assert database.budget(run_id).used.model_requests == 1
        too_low = amend_body(client, run_id, max_cost_microusd=1)
        rejected = client.post(
            "/api/v1/runs/" + run_id + "/budget-amendments", headers=headers(), json=too_low
        )
        assert rejected.status_code == 409 and rejected.json()["code"] == "BUDGET_BELOW_USAGE"
        assert len(database.interventions(run_id).budget_amendments) == 1


def test_operator_authority_is_explicit_and_project_scoped(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        run = wait_for(client, run_id, "needs_review")
        response = client.get("/api/v1/runs/" + run_id + "/interventions", headers=headers())
        assert response.status_code == 403
        for path in ("budget-amendments", "usage-reconciliations"):
            response = client.post(
                "/api/v1/runs/" + run_id + "/" + path, headers=headers(), json={}
            )
            assert response.status_code == 403
        response = client.get(
            "/api/v1/runs/" + run_id + "/interventions", headers=headers(token=RESTRICTED_TOKEN)
        )
        assert response.status_code == 403
        assert record(client, run_id).state.revision == run.state.revision


def test_concurrent_budget_authorizations_have_one_winner_and_auditable_history(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        wait_for(client, run_id, "needs_review")
        body = amend_body(client, run_id, max_active_seconds=240)

        def submit(_: int) -> int:
            return client.post(
                "/api/v1/runs/" + run_id + "/budget-amendments", headers=headers(), json=body
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(submit, (1, 2))) == [200, 409]
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert len(database.interventions(run_id).budget_amendments) == 1
        before = database.budget(run_id)
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        assert EditorialDatabase(tmp_path / "editorial.sqlite3").budget(run_id) == before
        assert (
            client.get("/api/v1/runs/" + run_id + "/interventions", headers=headers()).json()[
                "budget_policy"
            ]["max_active_seconds"]
            == 240
        )


def test_revoked_evidence_resubmission_invalidates_later_approvals_and_repeats_human_gates(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        run = wait_for(client, run_id, "waiting_review")
        assert run.state.node == "publish_review"
        decision = next(d for d in run.review_decisions if d.gate == "evidence")
        old_story = {d.decision_id for d in run.review_decisions if d.gate == "narrative"}
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-revocations",
            headers=headers(),
            json=dict(
                expected_revision=run.state.revision,
                decision_id=decision.decision_id,
                reason="Recheck evidence",
            ),
        )
        assert response.status_code == 200
        revoked = record(client, run_id)
        body = dict(
            expected_revision=revoked.state.revision,
            decision_id=decision.decision_id,
            reason="Submit unchanged targets for fresh human review",
        )
        same = headers("resubmit-evidence")
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-resubmissions", headers=same, json=body
        )
        assert response.status_code == 202, response.text
        assert (
            client.post(
                "/api/v1/runs/" + run_id + "/review-resubmissions", headers=same, json=body
            ).json()
            == response.json()
        )
        fresh = wait_for(client, run_id, "waiting_review")
        assert fresh.state.node == "evidence_review"
        assert fresh.state.research_rounds_started == run.state.research_rounds_started
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert old_story <= set(database.revoked_reviews(run_id))
        assert database.reviews(run_id) == run.review_decisions
        for _ in range(3):
            approve_gate(client, run_id)
        published = wait_for(client, run_id, "published")
        assert published.current_release_id is not None and published.current_release_id.endswith(
            "-review-1"
        )
        release = database.release(published.current_release_id)
        assert not old_story.intersection(release.manifest.review_decision_ids)
        assert len(database.interventions(run_id).review_resubmissions) == 1


def test_resubmission_does_not_overwrite_a_staged_release_with_old_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = PublicationService.stage
    old_ids: list[str] = []

    def stage(
        self: PublicationService,
        run: RunRecord,
        package: RuntimePackage,
        decision_ids: tuple[str, ...],
    ) -> ReleaseRecord:
        release = original(self, run, package, decision_ids)
        if not old_ids:
            old_ids.append(release.manifest.release_id)
            raise RuntimeError("Stop after immutable release preparation")
        return release

    monkeypatch.setattr(PublicationService, "stage", stage)
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        run = stopped(client, run_id, "failed")
        decision = next(d for d in run.review_decisions if d.gate == "narrative")
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-revocations",
            headers=headers(),
            json=dict(
                expected_revision=run.state.revision,
                decision_id=decision.decision_id,
                reason="Recheck staged story",
            ),
        )
        assert response.status_code == 200
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-resubmissions",
            headers=headers(),
            json=dict(
                expected_revision=record(client, run_id).state.revision,
                decision_id=decision.decision_id,
                reason="New review chain",
            ),
        )
        assert response.status_code == 202, response.text
        wait_for(client, run_id, "waiting_review")
        for _ in range(2):
            approve_gate(client, run_id)
        published = wait_for(client, run_id, "published")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert published.current_release_id != old_ids[0]
        assert database.release(old_ids[0]).status == "staged"
        assert (tmp_path / "releases/project-1" / old_ids[0] / "manifest.json").exists()
        decision = next(d for d in reversed(published.review_decisions) if d.gate == "publication")
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-revocations",
            headers=headers(),
            json=dict(
                expected_revision=published.state.revision,
                decision_id=decision.decision_id,
                reason="Retire this immutable publication",
            ),
        )
        assert response.status_code == 200 and database.current_release("project-1") is None
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-resubmissions",
            headers=headers(),
            json=dict(
                expected_revision=record(client, run_id).state.revision,
                decision_id=decision.decision_id,
                reason="Must create a replacement run",
            ),
        )
        assert response.status_code == 409 and response.json()["code"] == "INTERVENTION_NOT_ALLOWED"


def test_automatic_phases_are_metered_once_and_human_wait_does_not_spend_time(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        wait_for(client, run_id, "needs_review")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        before = database.budget(run_id).used.active_milliseconds
        time.sleep(0.06)
        assert database.budget(run_id).used.active_milliseconds == before
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        wait_for(client, run_id, "published")
        budget = database.budget(run_id)
        timed = [e for e in budget.entries if ":activity:" in e.operation_id]
        for phase in (
            "assemble_package",
            "validate_package",
            "publish_package",
            "gate-publication",
        ):
            assert any(":" + phase + ":" in e.operation_id for e in timed)
        assert all(
            e.settlement is not None and e.settlement.actual.active_milliseconds > 0 for e in timed
        )
        assert (
            sum(e.settlement.actual.active_milliseconds for e in timed if e.settlement)
            == budget.used.active_milliseconds
        )


def test_processing_overrun_before_publication_records_actual_time_and_keeps_pointer_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = PublicationService.stage
    elapsed = ActivityMeter.elapsed
    prepared = False

    def stage(
        self: PublicationService,
        run: RunRecord,
        package: RuntimePackage,
        decision_ids: tuple[str, ...],
    ) -> ReleaseRecord:
        nonlocal prepared
        result = original(self, run, package, decision_ids)
        prepared = True
        return result

    def overrun(self: ActivityMeter) -> int:
        return self.allowance + 1000 if prepared else elapsed(self)

    monkeypatch.setattr(PublicationService, "stage", stage)
    monkeypatch.setattr(ActivityMeter, "elapsed", overrun)
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        stopped(client, run_id, "budget_exhausted")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert prepared and database.current_release("project-1") is None
        assert database.budget(run_id).over_limit


def test_increasing_budget_does_not_release_unknown_usage_or_reset_limits(tmp_path: Path) -> None:
    tape = ProviderTape("unknown")
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        body = amend_body(client, run_id, max_model_requests=40)
        response = client.post(
            "/api/v1/runs/" + run_id + "/budget-amendments", headers=headers(), json=body
        )
        assert response.status_code == 200
        assert record(client, run_id).state.status == "needs_review"
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.budget(run_id).held.model_requests == 1
        too_low = amend_body(client, run_id, max_cost_microusd=1)
        response = client.post(
            "/api/v1/runs/" + run_id + "/budget-amendments", headers=headers(), json=too_low
        )
        assert response.status_code == 409 and response.json()["code"] == "BUDGET_BELOW_USAGE"
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(
                expected_revision=record(client, run_id).state.revision,
                reason="Cannot bypass unknown use",
            ),
        )
        assert response.status_code == 409 and len(tape.calls) == 1


def test_operator_permission_is_rechecked_before_idempotent_replay(tmp_path: Path) -> None:
    same = headers("withdraw-operator")
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        wait_for(client, run_id, "needs_review")
        body = amend_body(client, run_id, max_active_seconds=240)
        assert (
            client.post(
                "/api/v1/runs/" + run_id + "/budget-amendments", headers=same, json=body
            ).status_code
            == 200
        )
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/budget-amendments", headers=same, json=body
        )
        assert response.status_code == 403
        assert (
            len(
                EditorialDatabase(tmp_path / "editorial.sqlite3")
                .interventions(run_id)
                .budget_amendments
            )
            == 1
        )


def test_unknown_activity_is_reconciled_separately_without_repeating_saved_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pastport.adapters.content import LocalEvidenceAdapter
    from pastport.application.reliability import UsageSettlement
    from pastport.domain.evidence import SourceManifestDraft
    from pastport.domain.modules import InventoryRequest, ModuleResult
    from pastport.ports.modules import ExecutionContext

    finish = EditorialDatabase.finish_operation
    inventory = LocalEvidenceAdapter.inventory
    failed_once = False
    calls = 0

    async def count(
        self: LocalEvidenceAdapter, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        nonlocal calls
        calls += 1
        return await inventory(self, request, context)

    def lose_time(
        self: EditorialDatabase,
        operation_id: str,
        result_json: str,
        milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        nonlocal failed_once
        if ":activity:inventory_sources:" in operation_id and not failed_once:
            failed_once = True
            raise RuntimeError("Simulated loss of the activity settlement")
        finish(self, operation_id, result_json, milliseconds, settlement)

    monkeypatch.setattr(LocalEvidenceAdapter, "inventory", count)
    monkeypatch.setattr(EditorialDatabase, "finish_operation", lose_time)
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        stopped(client, run_id, "failed")
        assert calls == 1
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        resume(client, run_id)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(client, run_id, "settle", Usage(active_milliseconds=17))
        body["evidence"] = dict(
            kind="local_execution_record",
            reference="fixture-supervisor-time",
            description="Simulated external process timing receipt of 17 ms",
        )
        response = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
        )
        assert response.status_code == 200 and response.json()["state"]["status"] == "blocked"
        resume(client, run_id)
        wait_for(client, run_id, "needs_review")
        assert calls == 1
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.budget(run_id).used.active_milliseconds >= 17
        assert not database.budget(run_id).held.active_milliseconds


def test_budget_history_tampering_blocks_further_spending(tmp_path: Path) -> None:
    with TestClient(create_app(operator_settings(tmp_path))) as client:
        run_id = create_run(client)
        wait_for(client, run_id, "needs_review")
        body = amend_body(client, run_id, max_active_seconds=240)
        assert (
            client.post(
                "/api/v1/runs/" + run_id + "/budget-amendments", headers=headers(), json=body
            ).status_code
            == 200
        )
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        with database.connection() as connection:
            connection.execute("UPDATE budget_amendments SET sha256=?", ("0" * 64,))
            connection.commit()
        with pytest.raises(ServiceError) as failure:
            database.budget(run_id)
        assert failure.value.code == "AUDIT_CHANGED"


def test_concurrent_reconciliations_settle_the_same_usage_once(tmp_path: Path) -> None:
    tape = ProviderTape("unknown")
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(
            client,
            run_id,
            "recover",
            Usage(model_requests=1, input_tokens=100, output_tokens=20, cost_microusd=140),
        )

        def submit(_: int) -> int:
            return client.post(
                "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(submit, (1, 2))) == [200, 409]
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.budget(run_id).used.cost_microusd == 140
        assert len(database.interventions(run_id).reconciliations) == 1


def test_operator_cannot_authorize_a_third_attempt(tmp_path: Path) -> None:
    calls = 0

    def unavailable(request: ProviderRequest) -> ProviderResponse:
        nonlocal calls
        calls += 1
        raise ServiceError("OUTCOME_UNKNOWN", "Simulated uncertain dispatch")

    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(
            config,
            providers=(ProviderRegistration("fake", FakeModelProvider(unavailable)),),
            narrative_factory=GatewayNarrative,
        )
    ) as client:
        run_id = start(client)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(client, run_id, "retry", Usage())
        assert (
            client.post(
                "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
            ).status_code
            == 200
        )
        resume(client, run_id)
        stopped(client, run_id, "needs_review")
        body = reconcile_body(client, run_id, "retry", Usage())
        response = client.post(
            "/api/v1/runs/" + run_id + "/usage-reconciliations", headers=headers(), json=body
        )
        assert response.status_code == 409 and response.json()["code"] == "ATTEMPT_LIMIT"
        assert calls == 2


def test_v3_migration_preserves_model_requests_responses_and_existing_budget(
    tmp_path: Path,
) -> None:
    tape = ProviderTape()
    config = replace(operator_settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    with TestClient(
        create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
    ) as client:
        run_id = start(client)
        wait_for(client, run_id, "needs_review")
    database = EditorialDatabase(tmp_path / "editorial.sqlite3")
    before = database.budget(run_id)
    operation = next(e.operation_id for e in before.entries if ":model:" in e.operation_id)
    request = database.provider_request(operation)
    response = database.execution_receipt(operation)
    with database.connection() as connection:
        for table in ("usage_reconciliations", "budget_amendments", "review_resubmissions"):
            connection.execute("DROP TABLE " + table)
        connection.execute("UPDATE schema_versions SET version=3")
        connection.commit()
    database.initialize()
    assert database.budget(run_id) == before
    assert database.provider_request(operation) == request
    assert database.execution_receipt(operation) == response
    assert not database.interventions(run_id).reconciliations
    with database.connection() as connection:
        assert connection.execute("SELECT version FROM schema_versions").fetchone()[0] == 4
