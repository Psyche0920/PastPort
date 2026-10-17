"""Fault injection at business commits, reservations and private publication boundaries."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_service import approve_gate, confirm_direction, create_run, headers, settings, wait_for

from pastport.adapters.content import LocalEvidenceAdapter
from pastport.adapters.database import EditorialDatabase
from pastport.api.app import create_app
from pastport.api.settings import Credential
from pastport.application.models import Actor, RunRecord, ServiceError
from pastport.application.reliability import (
    OperationReservation,
    ReleaseRecord,
    Usage,
    UsageSettlement,
)
from pastport.application.updates import updated
from pastport.domain.common import ReviewDecision
from pastport.domain.evidence import SourceManifestDraft
from pastport.domain.modules import InventoryRequest, ModuleResult
from pastport.ports.modules import ExecutionContext


def paused_run(directory: Path) -> tuple[EditorialDatabase, RunRecord]:
    with TestClient(create_app(settings(directory))) as client:
        run_id = create_run(client)
        record = wait_for(client, run_id, "needs_review")
    database = EditorialDatabase(directory / "editorial.sqlite3")
    running = updated(
        record, state=updated(record.state, revision=record.state.revision + 1, status="running")
    )
    database.save(running, record.state.revision, "Begin isolated accounting exercise")
    return database, running


def reserve(run: RunRecord, suffix: str, usage: Usage) -> OperationReservation:
    return OperationReservation(
        operation_id=run.state.run_id + ":" + suffix,
        run_id=run.state.run_id,
        input_hash="a" * 64,
        reserved=usage,
        price_reference="fixed-test-price-v1",
    )


def test_ledger_reserves_settles_once_and_holds_unknown_usage(tmp_path: Path) -> None:
    database, run = paused_run(tmp_path)
    first = reserve(
        run,
        "provider-1",
        Usage(model_requests=2, input_tokens=20, output_tokens=10, cost_microusd=100000),
    )
    database.reserve_operation(first)
    with pytest.raises(ServiceError, match="remaining"):
        database.reserve_operation(reserve(run, "provider-2", Usage(model_requests=1)))
    settlement = UsageSettlement(
        actual=Usage(model_requests=1, input_tokens=5, output_tokens=2, cost_microusd=30),
        source="provider",
        provider_request_id="provider-test-1",
    )
    database.finish_operation(first.operation_id, '{"result":"recorded"}', 0, settlement)
    snapshot = database.budget(run.state.run_id)
    database.finish_operation(first.operation_id, '{"result":"recorded"}', 0, settlement)
    assert database.budget(run.state.run_id) == snapshot
    with pytest.raises(ServiceError, match="receipt cannot change"):
        database.finish_operation(
            first.operation_id,
            '{"result":"recorded"}',
            0,
            updated(settlement, actual=Usage(model_requests=2)),
        )
    second = reserve(run, "provider-2", Usage(model_requests=1, cost_microusd=99970))
    database.reserve_operation(second)
    database.recover_commands()
    restored = database.budget(run.state.run_id)
    assert restored.used.model_requests == 1
    assert restored.used.cost_microusd == 30
    assert restored.held.model_requests == 1
    assert restored.held.cost_microusd == 99970
    assert restored.entries[-1].state == "unknown"
    with pytest.raises(ServiceError, match="reconciliation"):
        database.operation_result(second.operation_id, second.input_hash)
    with pytest.raises(ServiceError, match="remaining"):
        database.reserve_operation(reserve(run, "provider-3", Usage(model_requests=1)))


def test_competing_budget_reservations_cannot_overspend(tmp_path: Path) -> None:
    database, run = paused_run(tmp_path)
    barrier = Barrier(2)

    def attempt(index: int) -> str:
        barrier.wait(timeout=5)
        try:
            database.reserve_operation(
                reserve(run, "concurrent-" + str(index), Usage(model_requests=2))
            )
            return "reserved"
        except ServiceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (1, 2)))
    assert sorted(results) == ["BUDGET_EXHAUSTED", "reserved"]
    assert database.budget(run.state.run_id).held.model_requests == 2


def test_price_attempt_limits_actual_overruns_and_input_hash_are_enforced(tmp_path: Path) -> None:
    database, run = paused_run(tmp_path)
    request = reserve(run, "price", Usage(model_requests=1))
    with pytest.raises(ServiceError, match="price"):
        database.reserve_operation(updated(request, price_reference=None))
    local = reserve(run, "local", Usage(active_milliseconds=100))
    for _ in range(2):
        database.reserve_operation(local)
        database.fail_operation(local.operation_id, 10)
    with pytest.raises(ServiceError, match="two total"):
        database.reserve_operation(local)
    with pytest.raises(ServiceError, match="dependencies"):
        database.operation_result(local.operation_id, "b" * 64)
    request = reserve(run, "overrun", Usage(cost_microusd=1))
    database.reserve_operation(request)
    database.finish_operation(
        request.operation_id,
        "saved",
        0,
        UsageSettlement(
            actual=Usage(cost_microusd=100001),
            source="provider",
            provider_request_id="unexpected-overrun",
        ),
    )
    snapshot = database.budget(run.state.run_id)
    assert snapshot.over_limit and snapshot.used.cost_microusd == 100001
    with pytest.raises(ServiceError, match="remaining"):
        database.reserve_operation(reserve(run, "next", Usage()))


def test_generic_state_save_cannot_forge_an_approval(tmp_path: Path) -> None:
    database, run = paused_run(tmp_path)
    fixture = json.loads((Path(__file__).parent / "fixtures/reference/bundle.json").read_text())
    fake = ReviewDecision.model_validate_json(json.dumps(fixture["reviews"]["decisions"][0]))
    forged = updated(
        run, review_decisions=(fake,), state=updated(run.state, revision=run.state.revision + 1)
    )
    with pytest.raises(ServiceError, match="review use case"):
        database.save(forged, run.state.revision, "Forged update")
    assert not database.reviews(run.state.run_id)
    assert database.run(run.state.run_id) == run


def test_editor_role_cannot_review_and_revocation_retires_release(tmp_path: Path) -> None:
    token = "editor-only-server-credential-for-reliability-tests"
    configuration = settings(tmp_path)
    configuration = replace(
        configuration,
        accounts=(
            *configuration.accounts,
            Credential(
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                actor=Actor(actor_id="editor-only", roles=("editor",), project_ids=("project-1",)),
            ),
        ),
    )
    with TestClient(create_app(configuration)) as client:
        run_id = create_run(client)
        direction = wait_for(client, run_id, "needs_review")
        comparison = next(
            item for item in direction.artifacts if item.reference.kind == "candidate_set"
        )
        denied_selection = client.post(
            "/api/v1/runs/" + run_id + "/candidate-selections",
            headers=headers(token=token),
            json=dict(
                expected_revision=direction.state.revision,
                candidate_set_hash=comparison.reference.sha256,
                candidate_id="candidate-1",
                reason="Wrong direction role",
            ),
        )
        assert denied_selection.status_code == 403
        confirm_direction(client, run_id)
        record = wait_for(client, run_id, "waiting_review")
        pending = next(
            item
            for item in record.review_requests
            if item.request_id == record.state.pending_review_id
        )
        rejected = client.post(
            "/api/v1/runs/" + run_id + "/review-decisions",
            headers=headers(token=token),
            json=dict(
                expected_revision=record.state.revision,
                request_id=pending.request_id,
                decisions=[
                    dict(
                        target_id=item.target_id,
                        target_version=item.version,
                        target_hash=item.sha256,
                        decision="approved",
                        reason="Wrong role",
                    )
                    for item in pending.targets
                ],
            ),
        )
        assert rejected.status_code == 403
        for _ in range(3):
            approve_gate(client, run_id)
        record = wait_for(client, run_id, "published")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.current_release("project-1") == record.current_release_id
        assert (
            client.get("/api/v1/projects/project-1/release", headers=headers()).status_code == 200
        )
        request = dict(
            expected_revision=record.state.revision,
            decision_id=record.review_decisions[0].decision_id,
            reason="Withdraw approval",
        )
        denied = client.post(
            "/api/v1/runs/" + run_id + "/review-revocations",
            headers=headers(token=token),
            json=request,
        )
        assert denied.status_code == 403
        request_headers = headers("same-revocation")
        revoked = client.post(
            "/api/v1/runs/" + run_id + "/review-revocations", headers=request_headers, json=request
        )
        assert revoked.status_code == 200, revoked.text
        replay = client.post(
            "/api/v1/runs/" + run_id + "/review-revocations", headers=request_headers, json=request
        )
        assert replay.json() == revoked.json()
        assert database.current_release("project-1") is None
        assert (
            client.get("/api/v1/projects/project-1/release", headers=headers()).status_code == 404
        )
        assert record.current_release_id is not None
        assert database.release(record.current_release_id).status == "retired"
        assert database.reviews(run_id) == record.review_decisions
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers())
        assert budget.status_code == 200 and budget.json()["held"]["active_milliseconds"] == 0


def test_saved_response_replays_without_another_module_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_inventory = LocalEvidenceAdapter.inventory
    original_finish = EditorialDatabase.finish_operation
    calls = 0
    failed = False

    async def inventory(
        self: LocalEvidenceAdapter, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        nonlocal calls
        calls += 1
        return await original_inventory(self, request, context)

    def finish(
        self: EditorialDatabase,
        operation_id: str,
        result_json: str,
        active_milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        nonlocal failed
        original_finish(self, operation_id, result_json, active_milliseconds, settlement)
        if not failed:
            failed = True
            raise RuntimeError("Injected failure after response and usage commit")

    monkeypatch.setattr(LocalEvidenceAdapter, "inventory", inventory)
    monkeypatch.setattr(EditorialDatabase, "finish_operation", finish)
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        stopped = wait_for(client, run_id, "failed")
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=stopped.state.revision, reason="Recover saved response"),
        )
        assert response.status_code == 202
        wait_for(client, run_id, "needs_review")
        assert calls == 1
        entries = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()[
            "entries"
        ]
        assert (
            len(
                [entry for entry in entries if entry["operation_id"].endswith(":inventory_sources")]
            )
            == 1
        )


def test_lost_response_holds_reservation_and_never_repeats_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_finish = EditorialDatabase.finish_operation
    original_inventory = LocalEvidenceAdapter.inventory
    calls = 0

    async def inventory(
        self: LocalEvidenceAdapter, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        nonlocal calls
        calls += 1
        return await original_inventory(self, request, context)

    def lose_response(
        self: EditorialDatabase,
        operation_id: str,
        result_json: str,
        active_milliseconds: int,
        settlement: UsageSettlement | None = None,
    ) -> None:
        if operation_id.endswith(":inventory_sources"):
            raise RuntimeError("Injected response loss before durable settlement")
        original_finish(self, operation_id, result_json, active_milliseconds, settlement)

    monkeypatch.setattr(LocalEvidenceAdapter, "inventory", inventory)
    with monkeypatch.context() as patch:
        patch.setattr(EditorialDatabase, "finish_operation", lose_response)
        with TestClient(create_app(settings(tmp_path))) as client:
            run_id = create_run(client)
            stopped = wait_for(client, run_id, "failed")
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=stopped.state.revision, reason="Check uncertain operation"),
        )
        assert response.status_code == 202
        uncertain = wait_for(client, run_id, "needs_review")
        assert (
            uncertain.state.last_error is not None
            and uncertain.state.last_error.code == "OUTCOME_UNKNOWN"
        )
        assert calls == 1
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        assert any(
            e["state"] == "unknown" and e["operation_id"].endswith(":inventory_sources")
            for e in budget["entries"]
        )
        assert budget["held"]["active_milliseconds"] == 0
        assert budget["used"]["active_milliseconds"] > 0


def stage_without_pointer(
    directory: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, RunRecord]:
    def fail_commit(self: EditorialDatabase, run: RunRecord, release: ReleaseRecord) -> RunRecord:
        raise RuntimeError("Injected crash after release rename before pointer transaction")

    with monkeypatch.context() as patch:
        patch.setattr(EditorialDatabase, "commit_release", fail_commit)
        with TestClient(create_app(settings(directory))) as client:
            run_id = create_run(client)
            confirm_direction(client, run_id)
            for _ in range(3):
                approve_gate(client, run_id)
            return run_id, wait_for(client, run_id, "failed")


@pytest.mark.parametrize("tamper", [None, "package.json", "synthetic-hatch.svg"])
def test_release_before_pointer_recovers_or_rejects_modified_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str | None
) -> None:
    run_id, stopped = stage_without_pointer(tmp_path, monkeypatch)
    database = EditorialDatabase(tmp_path / "editorial.sqlite3")
    assert database.current_release("project-1") is None
    release_id = "release-" + run_id
    assert database.release(release_id).status == "staged"
    directory = tmp_path / "releases/project-1" / release_id
    if tamper == "synthetic-hatch.svg":
        tamper = json.loads((directory / "package.json").read_text())["media_manifest"][0][
            "relative_path"
        ]
    if tamper:
        (directory / tamper).write_bytes(b"unapproved bytes")
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=stopped.state.revision, reason="Recover staged release"),
        )
        assert response.status_code == 202
        restored = wait_for(client, run_id, "failed" if tamper else "published")
        if tamper:
            assert database.current_release("project-1") is None
            assert (
                restored.state.last_error is not None
                and restored.state.last_error.code == "RELEASE_CHANGED"
            )
            assert (directory / tamper).read_bytes() == b"unapproved bytes"
        else:
            assert database.current_release("project-1") == release_id
            assert database.release(release_id).status == "published"


def test_post_commit_failure_cannot_undo_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = EditorialDatabase.commit_release

    def committed_then_failed(
        self: EditorialDatabase, run: RunRecord, release: ReleaseRecord
    ) -> RunRecord:
        original(self, run, release)
        raise RuntimeError("Injected process failure after publication commit")

    monkeypatch.setattr(EditorialDatabase, "commit_release", committed_then_failed)
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        record = wait_for(client, run_id, "published")
        assert (
            EditorialDatabase(tmp_path / "editorial.sqlite3").current_release("project-1")
            == record.current_release_id
        )
        response = client.post(
            "/api/v1/runs/" + run_id + "/cancel",
            headers=headers(),
            json=dict(expected_revision=record.state.revision, reason="Too late"),
        )
        assert response.status_code == 409


def test_reviewer_permission_loss_blocks_staged_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, stopped = stage_without_pointer(tmp_path, monkeypatch)
    configuration = settings(tmp_path)
    accounts = tuple(
        updated(account, actor=updated(account.actor, roles=("editor",)))
        for account in configuration.accounts
    )
    with TestClient(create_app(replace(configuration, accounts=accounts))) as client:
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(
                expected_revision=stopped.state.revision, reason="Revalidate reviewer authority"
            ),
        )
        assert response.status_code == 202
        result = wait_for(client, run_id, "needs_review")
        assert (
            result.state.last_error is not None
            and result.state.last_error.code == "APPROVAL_AUTHORITY_LOST"
        )
        assert (
            EditorialDatabase(tmp_path / "editorial.sqlite3").current_release("project-1") is None
        )


def test_pointer_cas_rejects_withdrawal_of_the_expected_old_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        first_id = create_run(client)
        confirm_direction(client, first_id)
        for _ in range(3):
            approve_gate(client, first_id)
        first = wait_for(client, first_id, "published")

        def fail_commit(
            self: EditorialDatabase, run: RunRecord, release: ReleaseRecord
        ) -> RunRecord:
            raise RuntimeError("Leave the next release staged")

        with monkeypatch.context() as patch:
            patch.setattr(EditorialDatabase, "commit_release", fail_commit)
            # The same registered project, rather than a second source identity.
            budget = json.loads(
                (Path(__file__).parent / "fixtures/reference/budget-policy.json").read_text()
            )
            response = client.post(
                "/api/v1/projects/project-1/runs",
                headers=headers(),
                json=dict(
                    budget_policy=budget,
                    policy_ref=client.get(
                        "/api/v1/projects/project-1/policy", headers=headers()
                    ).json(),
                ),
            )
            second_id = response.json()["state"]["run_id"]
            confirm_direction(client, second_id)
            for _ in range(3):
                approve_gate(client, second_id)
            second = wait_for(client, second_id, "failed")
        assert second.expected_old_release == first.current_release_id
        response = client.post(
            "/api/v1/runs/" + first_id + "/review-revocations",
            headers=headers(),
            json=dict(
                expected_revision=first.state.revision,
                decision_id=first.review_decisions[0].decision_id,
                reason="Earlier evidence withdrawn",
            ),
        )
        assert response.status_code == 200
        response = client.post(
            "/api/v1/runs/" + second_id + "/resume",
            headers=headers(),
            json=dict(expected_revision=second.state.revision, reason="Check expected pointer"),
        )
        assert response.status_code == 202
        conflict = wait_for(client, second_id, "failed")
        assert (
            conflict.state.last_error is not None
            and conflict.state.last_error.code == "RELEASE_CONFLICT"
        )
        assert (
            EditorialDatabase(tmp_path / "editorial.sqlite3").current_release("project-1") is None
        )


def test_existing_release_is_retired_when_reviewer_authority_is_removed(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        record = wait_for(client, run_id, "published")
    configuration = settings(tmp_path)
    configuration = replace(
        configuration,
        accounts=tuple(
            updated(account, actor=updated(account.actor, roles=("editor",)))
            for account in configuration.accounts
        ),
    )
    with TestClient(create_app(configuration)):
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.current_release("project-1") is None
        assert record.current_release_id is not None
        assert database.release(record.current_release_id).status == "retired"


@pytest.mark.parametrize("commit_response", [True, False])
def test_abrupt_process_exit_reconciles_business_state_before_graph(
    tmp_path: Path, commit_response: bool
) -> None:
    import os
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent("""
        import asyncio
        import os
        import sys
        import threading
        import time
        from pathlib import Path
        from fastapi.testclient import TestClient
        from pastport.adapters.content import LocalEvidenceAdapter
        from pastport.adapters.database import EditorialDatabase
        from pastport.api.app import create_app
        from test_service import create_run, settings
        directory = Path(sys.argv[1])
        commit = sys.argv[2] == "True"
        ready = threading.Event()
        original_finish = EditorialDatabase.finish_operation
        original_inventory = LocalEvidenceAdapter.inventory
        async def inventory(self, request, context):
            with (directory / "calls.txt").open("a") as stream:
                stream.write("inventory\\n")
                stream.flush()
                os.fsync(stream.fileno())
            return await original_inventory(self, request, context)
        def finish(self, operation_id, result_json, milliseconds, settlement=None):
            if not operation_id.endswith(":inventory_sources"):
                return original_finish(self, operation_id, result_json, milliseconds, settlement)
            if commit:
                original_finish(self, operation_id, result_json, milliseconds, settlement)
            ready.wait(5)
            os._exit(73)
        LocalEvidenceAdapter.inventory = inventory
        EditorialDatabase.finish_operation = finish
        with TestClient(create_app(settings(directory))) as client:
            run_id = create_run(client)
            (directory / "run-id.txt").write_text(run_id)
            ready.set()
            time.sleep(15)
        raise RuntimeError("Process did not reach the injected exit")
    """)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = (
        str(Path(__file__).parent) + os.pathsep + str(Path(__file__).parents[1] / "src")
    )
    environment["LANGSMITH_TRACING"] = "false"
    environment["LANGCHAIN_TRACING_V2"] = "false"
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(commit_response)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 73, result.stderr
    run_id = (tmp_path / "run-id.txt").read_text()
    with TestClient(create_app(settings(tmp_path))) as client:
        restored = wait_for(client, run_id, "needs_review")
        # The module receipt survives, while interrupted wall time now needs a
        # separate F6 operator reconciliation before any new automatic phase.
        assert restored.state.node == "inventory_sources"
        assert restored.state.last_error is not None
        assert restored.state.last_error.code == "OUTCOME_UNKNOWN"
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        if commit_response:
            assert database.operation_result(run_id + ":inventory_sources") is not None
        assert any(
            e.state == "unknown" and ":activity:" in e.operation_id
            for e in database.budget(run_id).entries
        )
        assert (tmp_path / "calls.txt").read_text().splitlines() == ["inventory"]
        budget = client.get("/api/v1/runs/" + run_id + "/budget", headers=headers()).json()
        inventory = [
            entry
            for entry in budget["entries"]
            if entry["operation_id"].endswith(":inventory_sources")
        ]
        assert len(inventory) == 1
        assert inventory[0]["state"] == ("settled" if commit_response else "unknown")


def test_cancellation_during_release_staging_cannot_switch_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pastport.application.publication import PublicationService
    from pastport.domain.packages import RuntimePackage

    original = PublicationService.stage

    def cancel_after_files(
        self: PublicationService,
        run: RunRecord,
        package: RuntimePackage,
        decision_ids: tuple[str, ...],
    ) -> ReleaseRecord:
        release = original(self, run, package, decision_ids)
        cancelled = updated(
            run, state=updated(run.state, revision=run.state.revision + 1, status="cancelled")
        )
        self.database.save(cancelled, run.state.revision, "Cancellation raced release preparation")
        return release

    monkeypatch.setattr(PublicationService, "stage", cancel_after_files)
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        record = wait_for(client, run_id, "cancelled")
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        assert database.current_release("project-1") is None
        assert record.current_release_id is None
        assert database.release("release-" + run_id).status == "staged"


def test_release_commit_is_idempotent_and_rejects_removed_review_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, stopped = stage_without_pointer(tmp_path, monkeypatch)
    database = EditorialDatabase(tmp_path / "editorial.sqlite3")
    release = database.release("release-" + run_id)
    running = updated(
        stopped, state=updated(stopped.state, revision=stopped.state.revision + 1, status="running")
    )
    database.save(running, stopped.state.revision, "Recover publication")
    missing_reviews = updated(running, review_requests=())
    with pytest.raises(ValueError):
        database.commit_release(missing_reviews, release)
    assert database.current_release("project-1") is None
    published = database.commit_release(running, release)
    assert database.commit_release(running, release) == published
    assert database.run(run_id) == published
    assert database.current_release("project-1") == published.current_release_id


def test_v1_migration_preserves_accounted_time_and_holds_unknown_usage(tmp_path: Path) -> None:
    import sqlite3

    database, run = paused_run(tmp_path / "seed")
    project = database.project(run.state.project_id)
    legacy = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(legacy) as connection:
        connection.executescript("""
            CREATE TABLE schema_versions(version INTEGER PRIMARY KEY);
            INSERT INTO schema_versions VALUES(1);
            CREATE TABLE projects(project_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                folder_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(provider,folder_id));
            CREATE TABLE workflow_runs(run_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL);
            CREATE TABLE execution_units(operation_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                result_json TEXT,
                active_milliseconds INTEGER NOT NULL DEFAULT 0);
        """)
        connection.execute(
            "INSERT INTO projects VALUES(?,?,?,?)",
            (project.project_id, project.provider, project.folder_id, project.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO workflow_runs VALUES(?,?,?,?,?)",
            (
                run.state.run_id,
                project.project_id,
                run.state.revision,
                run.state.status,
                run.model_dump_json(),
            ),
        )
        connection.execute(
            "INSERT INTO execution_units VALUES(?,'succeeded',?,77)",
            (run.state.run_id + ":saved", '{"old":"response"}'),
        )
        connection.execute(
            "INSERT INTO execution_units VALUES(?,'running',NULL,0)", (run.state.run_id + ":lost",)
        )
    migrated = EditorialDatabase(legacy)
    migrated.initialize()
    migrated.recover_commands()
    first = migrated.budget(run.state.run_id)
    assert first.used.active_milliseconds == 77
    assert first.held.active_milliseconds == run.budget_policy.max_active_seconds * 1000
    assert any(entry.state == "unknown" for entry in first.entries)
    assert migrated.operation_result(run.state.run_id + ":saved") == '{"old":"response"}'
    with pytest.raises(ServiceError, match="dependencies"):
        migrated.operation_result(run.state.run_id + ":saved", "a" * 64)
    migrated.initialize()
    assert migrated.budget(run.state.run_id) == first
    with sqlite3.connect(legacy) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_versions").fetchone() == (4,)


@pytest.mark.parametrize("tamper", ["result", "usage"])
def test_successful_execution_cannot_replay_a_broken_result_or_receipt(
    tmp_path: Path, tamper: str
) -> None:
    database, run = paused_run(tmp_path)
    request = reserve(run, "integrity", Usage(active_milliseconds=100))
    reservation_id = database.reserve_operation(request)
    database.finish_operation(request.operation_id, "saved typed response", 3)
    with database.connection() as connection:
        if tamper == "result":
            connection.execute(
                "UPDATE execution_units SET result_json='changed' WHERE operation_id=?",
                (request.operation_id,),
            )
        else:
            entry = database.budget(run.state.run_id).entries[-1]
            unknown = updated(entry, state="unknown", settlement=None)
            connection.execute(
                "UPDATE usage_ledger SET state='unknown',payload_json=? WHERE reservation_id=?",
                (unknown.model_dump_json(), reservation_id),
            )
        connection.commit()
    with pytest.raises(ServiceError) as failure:
        database.operation_result(request.operation_id, request.input_hash)
    assert failure.value.code == (
        "EXECUTION_RESULT_CHANGED" if tamper == "result" else "LEDGER_INCONSISTENT"
    )


def test_source_bytes_changed_during_publication_review_block_release(tmp_path: Path) -> None:
    import shutil

    content = tmp_path / "content"
    shutil.copytree(Path(__file__).parent / "fixtures/reference", content)
    directory = tmp_path / "data"
    configuration = replace(settings(directory), fixture_directory=content)
    with TestClient(create_app(configuration)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(2):
            approve_gate(client, run_id)
        pending = wait_for(client, run_id, "waiting_review")
        assert pending.state.node == "publish_review"
        (content / "synthetic-source.txt").write_text("Changed after the evidence was reviewed")
        approve_gate(client, run_id)
        refused = wait_for(client, run_id, "failed")
        assert (
            refused.state.last_error is not None
            and refused.state.last_error.code == "MEDIA_CHANGED"
        )
        assert (
            EditorialDatabase(directory / "editorial.sqlite3").current_release("project-1") is None
        )


def test_v2_migration_adds_execution_tables_without_changing_run_or_ledger(tmp_path: Path) -> None:
    database, run = paused_run(tmp_path)
    before = database.budget(run.state.run_id)
    with database.connection() as connection:
        for table in ("execution_grants", "execution_receipts", "provider_requests"):
            connection.execute("DROP TABLE " + table)
        connection.execute("UPDATE schema_versions SET version=2")
        connection.commit()
    database.initialize()
    assert database.run(run.state.run_id) == run
    assert database.budget(run.state.run_id) == before
    with database.connection() as connection:
        tables = {
            r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"execution_grants", "execution_receipts", "provider_requests"} <= tables
        assert connection.execute("SELECT version FROM schema_versions").fetchone()[0] == 4
