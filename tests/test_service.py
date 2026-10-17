"""Real SQLite, HTTP and LangGraph integration with explicitly synthetic content adapters."""

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pastport.api.app import create_app
from pastport.api.settings import AppSettings, Credential
from pastport.application.models import Actor, RunRecord

FIXTURES = Path(__file__).parent / "fixtures" / "reference"
TOKEN = "local-test-editor-token-with-more-than-32-characters"
RESTRICTED_TOKEN = "local-test-restricted-token-with-more-than-32-characters"


def settings(directory: Path, *, test_mode: bool = True) -> AppSettings:
    return AppSettings(
        data_directory=directory,
        environment="test" if test_mode else "production",
        fixture_directory=FIXTURES if test_mode else None,
        accounts=(
            Credential(
                token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
                actor=Actor(
                    actor_id="editor",
                    roles=("editor", "evidence", "narrative", "publisher"),
                    project_ids=None,
                ),
            ),
            Credential(
                token_sha256=hashlib.sha256(RESTRICTED_TOKEN.encode()).hexdigest(),
                actor=Actor(actor_id="outsider", roles=("editor",), project_ids=("other-project",)),
            ),
        ),
    )


def headers(key: str | None = None, token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": "Bearer " + token, "Idempotency-Key": key or str(uuid4())}


def project_body(project_id: str) -> dict[str, object]:
    return dict(
        name="Integration test project",
        provider="local_manifest",
        folder_id="folder-" + project_id,
        requirements=dict(
            project_id=project_id,
            schema_version="0.1.0",
            content_version="1",
            scope_site_ids=None,
            languages=["en", "zh"],
            target_story_minutes=5,
            theme_brief="Test the module connections",
            accessibility_requirements=["Equivalent text observation"],
            distribution_scope="internal_preview",
        ),
    )


def create_run(client: TestClient, project_id: str = "project-1") -> str:
    response = client.post("/api/v1/projects", json=project_body(project_id), headers=headers())
    assert response.status_code == 201, response.text
    budget = json.loads((FIXTURES / "budget-policy.json").read_text())
    response = client.post(
        "/api/v1/projects/" + project_id + "/runs",
        json=dict(
            budget_policy=budget,
            policy_ref=client.get(
                "/api/v1/projects/" + project_id + "/policy", headers=headers()
            ).json(),
        ),
        headers=headers(),
    )
    assert response.status_code == 202, response.text
    return str(response.json()["state"]["run_id"])


def wait_for(client: TestClient, run_id: str, status: str) -> RunRecord:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get("/api/v1/runs/" + run_id, headers=headers())
        assert response.status_code == 200, response.text
        record = RunRecord.model_validate_json(response.content)
        if record.state.status == status:
            return record
        if record.state.status in ("failed", "blocked", "budget_exhausted"):
            pytest.fail(str(record.state))
        time.sleep(0.03)
    pytest.fail("Run did not reach " + status)


def confirm_direction(client: TestClient, run_id: str) -> None:
    record = wait_for(client, run_id, "needs_review")
    comparison = next(item for item in record.artifacts if item.reference.kind == "candidate_set")
    candidate = json.loads(comparison.payload_json)["candidates"][0]
    response = client.post(
        "/api/v1/runs/" + run_id + "/candidate-selections",
        headers=headers(),
        json=dict(
            expected_revision=record.state.revision,
            candidate_set_hash=comparison.reference.sha256,
            candidate_id=candidate["candidate_id"],
            reason="Human test confirmation",
        ),
    )
    assert response.status_code == 202, response.text


def approve_gate(client: TestClient, run_id: str) -> None:
    record = wait_for(client, run_id, "waiting_review")
    pending = next(
        item for item in record.review_requests if item.request_id == record.state.pending_review_id
    )
    response = client.post(
        "/api/v1/runs/" + run_id + "/review-decisions",
        headers=headers(),
        json=dict(
            expected_revision=record.state.revision,
            request_id=pending.request_id,
            decisions=[
                dict(
                    target_id=item.target_id,
                    target_version=item.version,
                    target_hash=item.sha256,
                    decision="approved",
                    reason="Explicit synthetic test decision",
                )
                for item in pending.targets
            ],
        ),
    )
    assert response.status_code == 202, response.text


def test_authenticated_http_graph_reaches_test_release(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        record = wait_for(client, run_id, "published")
        assert record.environment == "test"
        assert {decision.actor_id for decision in record.review_decisions} == {"editor"}
        assert {decision.gate for decision in record.review_decisions} == {
            "evidence",
            "narrative",
            "publication",
        }
        assert record.current_release_id is not None
        assert (
            tmp_path / "releases" / "project-1" / record.current_release_id / "package.json"
        ).exists()
        assert client.get("/api/v1/public/projects/project-1/release").status_code == 404


def test_restart_preserves_pending_review_and_completed_operations(tmp_path: Path) -> None:
    configuration = settings(tmp_path)
    with TestClient(create_app(configuration)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        first = wait_for(client, run_id, "waiting_review")
    with TestClient(create_app(configuration)) as client:
        restored = client.get("/api/v1/runs/" + run_id, headers=headers()).json()
        assert restored["state"] == first.state.model_dump(mode="json")
        approve_gate(client, run_id)
        next_review = wait_for(client, run_id, "waiting_review")
        assert next_review.state.node == "narrative_review"
        assert next_review.state.research_rounds_started == 1


def test_authentication_project_scope_and_idempotent_creation(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/api/v1/projects").status_code == 401
        request_headers = headers("same-key")
        first = client.post(
            "/api/v1/projects", headers=request_headers, json=project_body("project-1")
        )
        second = client.post(
            "/api/v1/projects", headers=request_headers, json=project_body("project-1")
        )
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        different = client.post(
            "/api/v1/projects", headers=request_headers, json=project_body("project-2")
        )
        assert different.status_code == 409
        assert different.json()["code"] == "IDEMPOTENCY_CONFLICT"
        assert (
            client.get(
                "/api/v1/projects/project-1", headers=headers(token=RESTRICTED_TOKEN)
            ).status_code
            == 403
        )
        assert client.get("/api/v1/projects", headers=headers(token=RESTRICTED_TOKEN)).json() == []


def test_unconfigured_mode_blocks_without_synthetic_fallback(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, test_mode=False))) as client:
        run_id = create_run(client)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            record = RunRecord.model_validate_json(
                client.get("/api/v1/runs/" + run_id, headers=headers()).content
            )
            if record.state.status == "blocked":
                break
            time.sleep(0.03)
        assert record.state.last_error is not None
        assert record.state.last_error.code == "MODULE_NOT_CONFIGURED"
        assert len(record.artifacts) == 1
        assert record.artifacts[0].reference.kind == "model_config"
        assert record.artifacts[0].reference.artifact_id == run_id + ":execution-binding"


def test_cancel_does_not_grant_approval_or_allow_resume(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        record = wait_for(client, run_id, "needs_review")
        response = client.post(
            "/api/v1/runs/" + run_id + "/resume",
            headers=headers(),
            json=dict(
                expected_revision=record.state.revision,
                reason="Try bypassing direction decision",
            ),
        )
        assert response.status_code == 409
        response = client.post(
            "/api/v1/runs/" + run_id + "/cancel",
            headers=headers(),
            json=dict(expected_revision=record.state.revision, reason="Cancel test"),
        )
        assert response.status_code == 202
        assert response.json()["state"]["status"] == "cancelled"
        assert response.json()["review_decisions"] == []


def test_manual_revision_locks_and_fresh_review_reach_latest_release(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        approve_gate(client, run_id)
        record = wait_for(client, run_id, "waiting_review")
        draft = json.loads(
            next(
                item.payload_json
                for item in reversed(record.artifacts)
                if item.reference.artifact_id == run_id + ":draft"
            )
        )
        response = client.post(
            "/api/v1/runs/" + run_id + "/locks",
            headers=headers(),
            json=dict(
                expected_revision=record.state.revision,
                json_pointers=["/package/game/locales/0/entries/0/text"],
                reason="Protect wording",
            ),
        )
        assert response.status_code == 200, response.text
        revision = response.json()["state"]["revision"]
        draft["package"]["game"]["locales"][0]["entries"][0]["text"] = "Changed protected text"
        body = dict(
            expected_revision=revision,
            reason="Revise wording",
            replacement_story=draft,
            facts_changed=False,
        )
        rejected = client.post(
            "/api/v1/runs/" + run_id + "/revisions", headers=headers(), json=body
        )
        assert rejected.status_code == 409
        assert rejected.json()["code"] == "FIELD_LOCKED"
        original = json.loads(
            next(
                item.payload_json
                for item in record.artifacts
                if item.reference.artifact_id == run_id + ":draft"
            )
        )
        draft["package"]["game"]["locales"][0]["entries"][0]["text"] = original["package"]["game"][
            "locales"
        ][0]["entries"][0]["text"]
        draft["package"]["game"]["locales"][0]["entries"][1]["text"] = "Updated reviewed wording"
        accepted = client.post(
            "/api/v1/runs/" + run_id + "/revisions", headers=headers(), json=body
        )
        assert accepted.status_code == 202, accepted.text
        revised = RunRecord.model_validate_json(accepted.content)
        assert revised.state.pending_review_id != record.state.pending_review_id
        stale = client.post("/api/v1/runs/" + run_id + "/revisions", headers=headers(), json=body)
        assert stale.status_code == 409
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        final = wait_for(client, run_id, "published")
        runtime = json.loads(
            next(item.payload_json for item in final.artifacts if item.reference.kind == "runtime")
        )
        assert runtime["game"]["locales"][0]["entries"][1]["text"] == "Updated reviewed wording"
        assert runtime["content_version"].startswith("edit-")


def test_operation_recovery_keeps_unknown_outcomes_and_accumulated_time(tmp_path: Path) -> None:
    from pastport.adapters.database import EditorialDatabase
    from pastport.application.models import ServiceError
    from pastport.application.reliability import OperationReservation, Usage
    from pastport.application.updates import updated

    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        record = wait_for(client, run_id, "needs_review")
    database = EditorialDatabase(tmp_path / "editorial.sqlite3")
    running = updated(
        record, state=updated(record.state, revision=record.state.revision + 1, status="running")
    )
    database.save(running, record.state.revision, "Isolated recovery exercise")
    initial = database.budget(run_id).used.active_milliseconds
    request = OperationReservation(
        operation_id=run_id + ":exercise",
        run_id=run_id,
        input_hash="c" * 64,
        reserved=Usage(active_milliseconds=100),
    )
    database.reserve_operation(request)
    database.fail_operation(request.operation_id, 23)
    database.reserve_operation(request)
    database.recover_commands()
    with pytest.raises(ServiceError, match="reconciliation"):
        database.operation_result(request.operation_id, request.input_hash)
    second = updated(request, operation_id=run_id + ":index-exercise")
    database.reserve_operation(second)
    database.finish_operation(second.operation_id, '{"typed":"result"}', 12)
    database.recover_commands()
    assert database.operation_result(second.operation_id, second.input_hash) == '{"typed":"result"}'
    assert database.budget(run_id).used.active_milliseconds == initial + 35


def test_database_environment_and_unrelated_schema_are_protected(tmp_path: Path) -> None:
    import sqlite3

    from pastport.adapters.database import EditorialDatabase
    from pastport.application.models import ServiceError

    database = EditorialDatabase(tmp_path / "editorial.sqlite3")
    database.initialize()
    database.bind_environment("test")
    with pytest.raises(ServiceError, match="separate data"):
        database.bind_environment("production")
    other = tmp_path / "other.sqlite3"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE original(value TEXT)")
    with pytest.raises(ServiceError, match="unrelated"):
        EditorialDatabase(other).initialize()
    with sqlite3.connect(other) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("original",)]


def test_live_worker_lock_rejects_a_second_service(tmp_path: Path) -> None:
    from pastport.application.models import ServiceError

    configuration = settings(tmp_path)
    with TestClient(create_app(configuration)) as first:
        assert first.get("/api/v1/health").status_code == 200
        with pytest.raises(ServiceError, match="Another worker"):
            with TestClient(create_app(configuration)):
                pytest.fail("A second worker acquired the same data directory")
        assert first.get("/api/v1/health").status_code == 200


def test_stale_review_hash_and_policy_reference_are_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        record = wait_for(client, run_id, "waiting_review")
        pending = next(
            item
            for item in record.review_requests
            if item.request_id == record.state.pending_review_id
        )
        response = client.post(
            "/api/v1/runs/" + run_id + "/review-decisions",
            headers=headers(),
            json=dict(
                expected_revision=record.state.revision,
                request_id=pending.request_id,
                decisions=[
                    dict(
                        target_id=item.target_id,
                        target_version=item.version,
                        target_hash="0" * 64,
                        decision="approved",
                        reason="Stale hash",
                    )
                    for item in pending.targets
                ],
            ),
        )
        assert response.status_code == 409
        unchanged = RunRecord.model_validate_json(
            client.get("/api/v1/runs/" + run_id, headers=headers()).content
        )
        assert unchanged.state.revision == record.state.revision
        assert not unchanged.review_decisions
        policy = client.get("/api/v1/projects/project-1/policy", headers=headers()).json()
        policy["sha256"] = "0" * 64
        response = client.post(
            "/api/v1/projects/project-1/runs",
            headers=headers(),
            json=dict(
                budget_policy=json.loads((FIXTURES / "budget-policy.json").read_text()),
                policy_ref=policy,
            ),
        )
        assert response.status_code == 409
        assert response.json()["code"] == "POLICY_INVALID"
