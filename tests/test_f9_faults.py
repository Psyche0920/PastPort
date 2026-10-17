"""F9 fault acceptance across injected modules and actual process death boundaries."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from test_service import (
    FIXTURES,
    approve_gate,
    confirm_direction,
    create_run,
    headers,
    settings,
    wait_for,
)
from test_shared_execution import GatewayNarrative, ProviderTape, execution

from pastport.adapters.database import EditorialDatabase
from pastport.api.app import create_app
from pastport.application.models import RunRecord, ServiceError
from pastport.application.reliability import ReleaseRecord
from pastport.development.reference_modules import ReferenceEvidence, ReferenceNarrative


@pytest.mark.parametrize(
    "evidence_injected,narrative_injected",
    [
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_revocation_between_staging_and_commit_blocks_every_module_combination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_injected: bool,
    narrative_injected: bool,
) -> None:
    prepared, proceed, attempted = Event(), Event(), Event()
    rejected: list[str] = []
    original = EditorialDatabase.commit_release

    def pause(self: EditorialDatabase, run: RunRecord, release: ReleaseRecord) -> RunRecord:
        prepared.set()
        if not proceed.wait(10):
            raise RuntimeError("Test did not release publication barrier")
        try:
            return original(self, run, release)
        except ServiceError as error:
            rejected.append(error.code)
            raise
        finally:
            attempted.set()

    monkeypatch.setattr(EditorialDatabase, "commit_release", pause)
    with TestClient(
        create_app(
            settings(tmp_path),
            evidence=ReferenceEvidence(FIXTURES) if evidence_injected else None,
            narrative=ReferenceNarrative(FIXTURES) if narrative_injected else None,
        )
    ) as client:
        try:
            run_id = create_run(client, "fixture-project")
            confirm_direction(client, run_id)
            for _ in range(3):
                approve_gate(client, run_id)
            assert prepared.wait(10)
            database = EditorialDatabase(tmp_path / "editorial.sqlite3")
            run = database.run(run_id)
            decision = next(item for item in run.review_decisions if item.gate == "evidence")
            response = client.post(
                f"/api/v1/runs/{run_id}/review-revocations",
                headers=headers(),
                json={
                    "expected_revision": run.state.revision,
                    "decision_id": decision.decision_id,
                    "reason": "Withdraw at commit barrier",
                },
            )
            assert response.status_code == 200, response.text
        finally:
            proceed.set()
        assert attempted.wait(10)
        assert rejected == ["REVIEW_REVOKED"]
        wait_for(client, run_id, "needs_review")
        assert database.current_release("fixture-project") is None
        assert decision.decision_id in database.revoked_reviews(run_id)
        assert (
            client.get("/api/v1/projects/fixture-project/release", headers=headers()).status_code
            == 404
        )
        assert database.reviews(run_id) == run.review_decisions


def crash_process(directory: Path, boundary: str, after: bool) -> str:
    script = textwrap.dedent("""
        import os
        import sys
        import threading
        import time
        from dataclasses import replace
        from pathlib import Path
        from fastapi.testclient import TestClient
        from pastport.adapters.database import EditorialDatabase
        from pastport.api.app import create_app
        from pastport.development.reference_modules import ReferenceEvidence, ReferenceNarrative
        from test_service import FIXTURES, approve_gate, confirm_direction, create_run, settings
        from test_shared_execution import SKILLS, GatewayNarrative, ProviderTape, execution, start

        directory, boundary, after = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "True"
        ready = threading.Event()
        if boundary == "publication":
            original = EditorialDatabase.commit_release
            def commit(self, run, release):
                if after:
                    original(self, run, release)
                if not ready.wait(10):
                    raise RuntimeError("Run identity was not saved")
                os._exit(74)
            EditorialDatabase.commit_release = commit
            app = create_app(settings(directory), evidence=ReferenceEvidence(FIXTURES),
                             narrative=ReferenceNarrative(FIXTURES))
        else:
            original = EditorialDatabase.save_execution_receipt
            def receipt(self, operation_id, run_id, receipt):
                if after:
                    original(self, operation_id, run_id, receipt)
                if not ready.wait(10):
                    raise RuntimeError("Run identity was not saved")
                os._exit(74)
            EditorialDatabase.save_execution_receipt = receipt
            tape = ProviderTape()
            def provider(request):
                with (directory / "provider-calls.txt").open("a") as stream:
                    stream.write(request.request_key + "\\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                return tape.respond(request)
            from pastport.adapters.model_provider import FakeModelProvider
            from pastport.application.execution_models import ProviderRegistration
            config = replace(settings(directory), execution=execution(), skill_directory=SKILLS)
            providers = (ProviderRegistration("fake", FakeModelProvider(provider)),)
            app = create_app(config, providers=providers, narrative_factory=GatewayNarrative)
        with TestClient(app) as client:
            if boundary == "publication":
                run_id = create_run(client, "fixture-project")
            else:
                run_id = start(client)
            with (directory / "run-id.txt").open("w") as stream:
                stream.write(run_id)
                stream.flush()
                os.fsync(stream.fileno())
            ready.set()
            if boundary == "publication":
                confirm_direction(client, run_id)
                for _ in range(3):
                    approve_gate(client, run_id)
            time.sleep(20)
        raise RuntimeError("Injected process exit was not reached")
    """)
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(Path(__file__).parent.resolve()), str(Path(__file__).parents[1].resolve() / "src"))
        ),
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }
    result = subprocess.run(
        [sys.executable, "-c", script, str(directory), boundary, str(after)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 74, result.stderr
    return (directory / "run-id.txt").read_text()


@pytest.mark.parametrize("after_commit", [False, True])
def test_actual_process_death_preserves_publication_atomicity(
    tmp_path: Path, after_commit: bool
) -> None:
    run_id = crash_process(tmp_path, "publication", after_commit)
    database = EditorialDatabase(tmp_path / "editorial.sqlite3")
    before = database.run(run_id)
    release_id = "release-" + run_id
    assert database.release(release_id).status == ("published" if after_commit else "staged")
    assert database.current_release("fixture-project") == (release_id if after_commit else None)
    files = tuple(sorted((tmp_path / "releases/fixture-project" / release_id).rglob("*")))
    payloads = {str(path): path.read_bytes() for path in files if path.is_file()}
    with TestClient(
        create_app(
            settings(tmp_path),
            evidence=ReferenceEvidence(FIXTURES),
            narrative=ReferenceNarrative(FIXTURES),
        )
    ) as client:
        restored = wait_for(client, run_id, "published" if after_commit else "needs_review")
        if after_commit:
            assert restored.current_release_id == release_id
            assert database.reviews(run_id) == before.review_decisions
            assert (
                client.get(
                    "/api/v1/projects/fixture-project/release", headers=headers()
                ).status_code
                == 200
            )
        else:
            assert restored.state.last_error and restored.state.last_error.code == "OUTCOME_UNKNOWN"
            assert any(
                item.state == "unknown" and ":activity:" in item.operation_id
                for item in database.budget(run_id).entries
            )
            assert (
                client.post(
                    f"/api/v1/runs/{run_id}/resume",
                    headers=headers(),
                    json={
                        "expected_revision": restored.state.revision,
                        "reason": "Cannot erase unknown time",
                    },
                ).status_code
                == 409
            )
            assert database.current_release("fixture-project") is None
        assert all(Path(path).read_bytes() == content for path, content in payloads.items())
        assert len(tuple((tmp_path / "releases/fixture-project").iterdir())) == 1


@pytest.mark.parametrize("after_receipt", [False, True])
def test_actual_process_death_never_redispatches_unknown_or_saved_model_response(
    tmp_path: Path,
    after_receipt: bool,
) -> None:
    from dataclasses import replace

    from test_shared_execution import SKILLS

    run_id = crash_process(tmp_path, "model_receipt", after_receipt)
    original_calls = (tmp_path / "provider-calls.txt").read_text().splitlines()
    assert len(original_calls) == 1
    tape = ProviderTape()
    config = replace(settings(tmp_path), execution=execution(), skill_directory=SKILLS)
    for _ in range(2):
        with TestClient(
            create_app(config, providers=tape.registration(), narrative_factory=GatewayNarrative)
        ) as client:
            restored = wait_for(client, run_id, "needs_review")
            assert restored.state.last_error and restored.state.last_error.code == "OUTCOME_UNKNOWN"
            database = EditorialDatabase(tmp_path / "editorial.sqlite3")
            budget = database.budget(run_id)
            entries = [item for item in budget.entries if ":model:" in item.operation_id]
            assert len(entries) == 1
            entry = entries[0]
            assert entry.state == ("settled" if after_receipt else "unknown")
            assert database.provider_request(entry.operation_id) is not None
            assert (database.execution_receipt(entry.operation_id) is not None) == after_receipt
            assert budget.used.model_requests == int(after_receipt)
            assert budget.held.model_requests == int(not after_receipt)
            assert any(
                item.state == "unknown" and ":activity:" in item.operation_id
                for item in budget.entries
            )
            assert (
                client.post(
                    f"/api/v1/runs/{run_id}/resume",
                    headers=headers(),
                    json={
                        "expected_revision": restored.state.revision,
                        "reason": "Do not retry unknown calls",
                    },
                ).status_code
                == 409
            )
            assert not tape.calls
            assert database.current_release(restored.state.project_id) is None
            assert (tmp_path / "provider-calls.txt").read_text().splitlines() == original_calls
