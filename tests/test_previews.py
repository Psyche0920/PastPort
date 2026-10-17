"""Actual draft previews before approval, private resources and isolation boundaries."""

from pathlib import Path

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

from pastport.api.app import create_app
from pastport.application.models import RunRecord


def narrative_review(client: TestClient) -> tuple[str, RunRecord]:
    run_id = create_run(client)
    confirm_direction(client, run_id)
    approve_gate(client, run_id)
    run = wait_for(client, run_id, "waiting_review")
    assert run.state.node == "narrative_review"
    return run_id, run


def preview_request(run: RunRecord) -> dict[str, object]:
    ref = next(
        item.reference
        for item in reversed(run.artifacts)
        if item.reference.artifact_id.endswith(":draft")
    )
    return {"expected_revision": run.state.revision, "source_ref": ref.model_dump(mode="json")}


def test_before_approval_preview_is_playable_private_and_survives_restart(tmp_path: Path) -> None:
    configuration = settings(tmp_path)
    with TestClient(create_app(configuration)) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        assert client.post(base, json=preview_request(run)).status_code == 401
        assert (
            client.post(
                base, headers=headers(token=RESTRICTED_TOKEN), json=preview_request(run)
            ).status_code
            == 403
        )
        response = client.post(base, headers=headers("create-preview"), json=preview_request(run))
        assert response.status_code == 200, response.text
        view = response.json()
        preview_id = view["preview_id"]
        assert view["kind"] == "test" and view["state"]["release_id"] == "preview:" + preview_id
        assert view["state"]["revision"] == 0
        request = {
            "project_id": view["project_id"],
            "release_id": view["state"]["release_id"],
            "package_hash": view["runtime_ref"]["sha256"],
            "action": {
                "action_id": "observe-preview",
                "expected_revision": 0,
                "kind": "observe",
                "target_id": "inspect-hatch",
                "spot_id": "hatch",
            },
        }
        result = client.post(base + f"/{preview_id}/actions", headers=headers(), json=request)
        assert result.status_code == 200, result.text
        expected = result.json()["result"]["state"]
        assert expected["revision"] == 1 and expected["inventory"] == ["delivery-note"]
        assert (
            client.post(base, headers=headers("create-preview"), json=preview_request(run)).json()[
                "state"
            ]
            == expected
        )
        resource = client.get(base + f"/{preview_id}/assets/asset-hatch", headers=headers())
        assert resource.status_code == 200 and resource.headers["cache-control"] == "no-store"
        assert resource.headers["content-type"].startswith("image/svg+xml")
        assert (
            client.get(base + f"/{preview_id}/assets/not-in-package", headers=headers()).status_code
            == 404
        )
        assert (
            client.get("/api/v1/projects/project-1/release", headers=headers()).status_code == 404
        )
        after = client.get(f"/api/v1/runs/{run_id}", headers=headers()).json()
        assert after["state"]["revision"] == run.state.revision
        assert after["review_decisions"] == [
            item.model_dump(mode="json") for item in run.review_decisions
        ]
        assert after["current_release_id"] is None
    with TestClient(create_app(configuration)) as client:
        restored = client.get(base + f"/{preview_id}", headers=headers())
        assert restored.status_code == 200, restored.text
        assert restored.json()["state"] == expected
        replay = client.post(base + f"/{preview_id}/actions", headers=headers(), json=request)
        assert replay.status_code == 200 and replay.json()["result"]["emitted_events"] == []
        assert replay.json()["result"]["state"] == expected


def test_current_session_and_static_allowlist_reveal_no_private_files(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/api/v1/session").status_code == 401
        session = client.get("/api/v1/session", headers=headers())
        assert session.status_code == 200
        assert set(session.json()) == {"actor_id", "roles", "project_ids", "environment"}
        assert session.json()["actor_id"] == "editor"
        for path in ["/static/player/runtime.mjs", "/static/workbench/api-client.mjs"]:
            result = client.get(path)
            assert result.status_code == 200 and "javascript" in result.headers["content-type"]
        for name in ["runner.mjs", "vectors.mjs", "contracts.d.ts", "__init__.py", "missing.mjs"]:
            assert client.get("/static/player/" + name).status_code == 404
        assert client.get("/static/workbench/app.py").status_code == 404


def test_preview_request_identity_cannot_be_forged_or_rebound(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        body = preview_request(run)
        assert (
            client.post(
                base, headers={"Authorization": headers()["Authorization"]}, json=body
            ).status_code
            == 422
        )
        wrong = {**body, "expected_revision": 0}
        assert client.post(base, headers=headers(), json=wrong).status_code == 409
        raw_reference = body["source_ref"]
        assert isinstance(raw_reference, dict)
        reference = dict(raw_reference)
        wrong = {**body, "source_ref": {**reference, "sha256": "0" * 64}}
        assert client.post(base, headers=headers(), json=wrong).status_code == 409
        result = client.post(base, headers=headers("bounded-key"), json=body)
        assert result.status_code == 200, result.text
        view = result.json()
        conflict = client.post(
            base, headers=headers("bounded-key"), json={**body, "expected_revision": 0}
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
        extras: tuple[dict[str, object], ...] = (
            {"state": {}},
            {"owner": "other"},
            {"kind": "release"},
        )
        for extra in extras:
            assert client.post(base, headers=headers(), json={**body, **extra}).status_code == 422
        action = {
            "project_id": "project-1",
            "release_id": "release-test-1",
            "package_hash": view["runtime_ref"]["sha256"],
            "action": {
                "action_id": "wrong-binding",
                "expected_revision": 0,
                "kind": "observe",
                "target_id": "inspect-hatch",
                "spot_id": "hatch",
            },
        }
        failed = client.post(
            base + "/" + view["preview_id"] + "/actions", headers=headers(), json=action
        )
        assert failed.status_code == 409 and failed.json()["code"] == "PLAYER_IDENTITY_MISMATCH"
        assert (
            client.get(base + "/" + view["preview_id"], headers=headers()).json()["state"][
                "revision"
            ]
            == 0
        )


def test_sources_require_exact_identity_and_never_invent_missing_extraction(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        from pastport.domain.evidence import EvidencePackage

        evidence = EvidencePackage.model_validate_json(
            next(
                item.payload_json
                for item in reversed(run.artifacts)
                if item.reference.artifact_id.endswith(":evidence")
            )
        )
        source = evidence.sources[0]
        base = f"/api/v1/runs/{run_id}/sources/{source.source_id}"
        query = {"source_version": source.version, "file_sha256": source.file_sha256}
        assert client.get(base, headers=headers()).status_code == 422
        assert (
            client.get(
                base, headers=headers(), params={**query, "file_sha256": "0" * 64}
            ).status_code
            == 404
        )
        assert (
            client.get(base, headers=headers(token=RESTRICTED_TOKEN), params=query).status_code
            == 403
        )
        document = client.get(base, headers=headers(), params=query)
        assert document.status_code == 200, document.text
        assert document.json()["source"]["file_sha256"] == source.file_sha256
        assert document.json()["fragments"] == [] and document.json()["status"] == "failed"
        content = client.get(base + "/content", headers=headers(), params=query)
        assert content.status_code == 200 and content.headers["content-disposition"] == "attachment"
        import hashlib

        assert hashlib.sha256(content.content).hexdigest() == source.file_sha256
        assert content.headers["x-content-type-options"] == "nosniff"


def test_private_release_package_and_assets_are_pinned_to_current_identity(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, _ = narrative_review(client)
        approve_gate(client, run_id)
        approve_gate(client, run_id)
        run = wait_for(client, run_id, "published")
        base = f"/api/v1/projects/project-1/releases/{run.current_release_id}"
        assert client.get(base + "/package").status_code == 401
        assert (
            client.get(base + "/package", headers=headers(token=RESTRICTED_TOKEN)).status_code
            == 403
        )
        result = client.get(base + "/package", headers=headers())
        assert result.status_code == 200, result.text
        assert run.state.runtime_ref is not None
        assert result.json()["runtime_ref"] == run.state.runtime_ref.model_dump(mode="json")
        # Already assembled runtime snapshots also use the isolated preview namespace.
        projected = client.post(
            f"/api/v1/runs/{run_id}/previews",
            headers=headers(),
            json={
                "expected_revision": run.state.revision,
                "source_ref": run.state.runtime_ref.model_dump(mode="json"),
            },
        )
        assert projected.status_code == 200, projected.text
        assert projected.json()["state"]["release_id"].startswith("preview:")
        assert client.get(base + "/assets/asset-hatch", headers=headers()).status_code == 200
        assert client.get(base + "/assets/unknown", headers=headers()).status_code == 404
        assert (
            client.get(
                "/api/v1/projects/project-1/releases/wrong/package", headers=headers()
            ).status_code
            == 404
        )
        package_path = (
            tmp_path / "releases" / "project-1" / str(run.current_release_id) / "package.json"
        )
        package_path.write_text("{}")
        assert client.get(base + "/package", headers=headers()).status_code == 404
        assert client.get(base + "/assets/asset-hatch", headers=headers()).status_code == 404


def test_draft_change_and_run_cancellation_invalidate_bound_previews(tmp_path: Path) -> None:
    import json

    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        view = client.post(base, headers=headers(), json=preview_request(run)).json()
        draft = json.loads(
            next(
                item.payload_json
                for item in reversed(run.artifacts)
                if item.reference.artifact_id.endswith(":draft")
            )
        )
        draft["package"]["game"]["locales"][0]["entries"][0]["text"] += " Changed for preview test"
        result = client.post(
            f"/api/v1/runs/{run_id}/revisions",
            headers=headers(),
            json={
                "expected_revision": run.state.revision,
                "reason": "Update a text fragment",
                "replacement_story": draft,
                "facts_changed": False,
            },
        )
        assert result.status_code == 202, result.text
        stale = client.get(base + "/" + view["preview_id"], headers=headers())
        assert stale.status_code == 409 and stale.json()["code"] == "PREVIEW_INVALIDATED"
        current = wait_for(client, run_id, "waiting_review")
        new = client.post(base, headers=headers(), json=preview_request(current))
        assert new.status_code == 200, new.text
        client.post(
            f"/api/v1/runs/{run_id}/cancel",
            headers=headers(),
            json={"expected_revision": current.state.revision, "reason": "Stop this test run"},
        )
        cancelled = client.get(base + "/" + new.json()["preview_id"], headers=headers())
        assert cancelled.status_code == 409 and cancelled.json()["code"] == "PREVIEW_INVALIDATED"


def test_expired_preview_and_same_key_retry_are_refused_without_reset(tmp_path: Path) -> None:
    import sqlite3
    from datetime import UTC, datetime, timedelta

    from pastport.adapters.previews import SQLitePreviews
    from pastport.application.previews import PreviewRecord
    from pastport.application.updates import updated
    from pastport.domain.common import CanonicalSerializer

    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        view = client.post(base, headers=headers("expire-key"), json=preview_request(run)).json()
        path = tmp_path / "previews.sqlite3"
        with sqlite3.connect(path) as connection:
            original = PreviewRecord.model_validate_json(
                connection.execute("SELECT payload_json FROM preview_records").fetchone()[0]
            )
            expired = updated(original, expires_at=datetime.now(UTC) - timedelta(seconds=1))
            connection.execute(
                "UPDATE preview_records SET payload_json=?, sha256=?, expires_at=?",
                (
                    expired.model_dump_json(),
                    CanonicalSerializer.digest(expired),
                    expired.expires_at.isoformat(),
                ),
            )
        for result in [
            client.get(base + "/" + view["preview_id"], headers=headers()),
            client.post(base, headers=headers("expire-key"), json=preview_request(run)),
            client.get(base + "/" + view["preview_id"] + "/assets/asset-hatch", headers=headers()),
        ]:
            assert result.status_code == 410 and result.json()["code"] == "PREVIEW_EXPIRED"
        assert SQLitePreviews(path, "test").state(expired).revision == 0


def test_same_project_accounts_cannot_read_or_advance_each_others_previews(tmp_path: Path) -> None:
    import hashlib
    from dataclasses import replace

    from pastport.api.settings import Credential
    from pastport.application.models import Actor

    token = "another-local-test-account-token-longer-than-32-characters"
    configuration = settings(tmp_path)
    configuration = replace(
        configuration,
        accounts=configuration.accounts
        + (
            Credential(
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                actor=Actor(
                    actor_id="second-reviewer", roles=("narrative",), project_ids=("project-1",)
                ),
            ),
        ),
    )
    with TestClient(create_app(configuration)) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        first = client.post(base, headers=headers("same-key"), json=preview_request(run)).json()
        other = client.post(base, headers=headers("same-key", token), json=preview_request(run))
        assert other.status_code == 200, other.text
        assert other.json()["preview_id"] != first["preview_id"]
        assert (
            client.get(base + "/" + first["preview_id"], headers=headers(token=token)).status_code
            == 404
        )
        assert (
            client.get(
                base + "/" + first["preview_id"] + "/assets/asset-hatch",
                headers=headers(token=token),
            ).status_code
            == 404
        )
        assert client.get(base + "/" + first["preview_id"], headers=headers()).status_code == 200


def test_preview_quota_is_atomic_under_concurrent_creation_and_does_not_evict(
    tmp_path: Path,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime

    from pastport.adapters.previews import SQLitePreviews
    from pastport.application.models import ServiceError
    from pastport.application.updates import updated

    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        view = client.post(base, headers=headers("first-key"), json=preview_request(run)).json()
        repository = SQLitePreviews(tmp_path / "previews.sqlite3", "test")
        actor = settings(tmp_path).accounts[0].actor
        record = repository.get(actor, run_id, view["preview_id"])
        initial = repository.state(record)

        def create(number: int) -> str:
            candidate = updated(record, preview_id=f"session-{number}", request_key=f"key-{number}")
            state = updated(initial, release_id="preview:" + candidate.preview_id)
            try:
                return repository.create_preview(candidate, state, datetime.now(UTC)).preview_id
            except ServiceError as error:
                return error.code

        for number in range(1, 9):
            assert create(number) == f"session-{number}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, [9, 10]))
        assert results.count("PREVIEW_LIMIT_REACHED") == 1
        assert repository.state(record) == initial
        assert (
            client.post(base, headers=headers("full-quota"), json=preview_request(run)).json()[
                "code"
            ]
            == "PREVIEW_LIMIT_REACHED"
        )
        # An existing key still restores its own save at the quota boundary.
        assert (
            client.post(base, headers=headers("first-key"), json=preview_request(run)).status_code
            == 200
        )


def test_registered_source_and_media_changes_block_existing_preview(tmp_path: Path) -> None:
    import shutil
    from dataclasses import replace

    from test_service import FIXTURES

    resources = tmp_path / "resources"
    shutil.copytree(FIXTURES, resources)
    configuration = replace(settings(tmp_path), resource_directory=resources)
    with TestClient(create_app(configuration)) as client:
        run_id, run = narrative_review(client)
        base = f"/api/v1/runs/{run_id}/previews"
        view = client.post(base, headers=headers(), json=preview_request(run)).json()
        source = resources / "synthetic-source.txt"
        source.write_bytes(source.read_bytes() + b"tampered")
        result = client.get(base + "/" + view["preview_id"], headers=headers())
        assert result.status_code == 409 and result.json()["code"] == "MEDIA_CHANGED"
        assert (
            client.get(
                base + "/" + view["preview_id"] + "/assets/asset-hatch", headers=headers()
            ).status_code
            == 409
        )


def test_stored_original_fragments_are_returned_with_exact_source_identity(tmp_path: Path) -> None:
    from pastport.adapters.database import EditorialDatabase
    from pastport.application.models import StoredArtifact
    from pastport.application.updates import updated
    from pastport.domain.common import ArtifactRef, CanonicalSerializer, SourceLocator
    from pastport.domain.evidence import EvidencePackage
    from pastport.domain.modules import LocatedText, SourceDocument

    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        evidence = EvidencePackage.model_validate_json(
            next(
                item.payload_json
                for item in run.artifacts
                if item.reference.artifact_id.endswith(":evidence")
            )
        )
        source = evidence.sources[0]
        document = SourceDocument(
            source=source,
            status="read",
            fragments=(
                LocatedText(
                    locator=SourceLocator(
                        source_id=source.source_id,
                        source_version=source.version,
                        file_sha256=source.file_sha256,
                        page_index=None,
                        printed_page=None,
                        paragraph_or_region="saved-fragment-1",
                    ),
                    text="Saved original text from registered source",
                ),
            ),
        )
        stored = StoredArtifact(
            reference=ArtifactRef(
                artifact_id=run_id + ":source-document",
                project_id=run.state.project_id,
                kind="report",
                schema_version="0.1.0",
                content_version="source-document-1",
                sha256=CanonicalSerializer.digest(document),
            ),
            payload_json=document.model_dump_json(),
        )
        database = EditorialDatabase(tmp_path / "editorial.sqlite3")
        database.save(
            updated(
                run,
                state=updated(run.state, revision=run.state.revision + 1),
                artifacts=(*run.artifacts, stored),
            ),
            run.state.revision,
            "Record source extraction fixture",
        )
        result = client.get(
            f"/api/v1/runs/{run_id}/sources/{source.source_id}",
            headers=headers(),
            params={"source_version": source.version, "file_sha256": source.file_sha256},
        )
        assert result.status_code == 200, result.text
        assert result.json() == document.model_dump(mode="json")


def test_shared_client_module_checks() -> None:
    import subprocess

    result = subprocess.run(
        ["node", "--test", "tests/api-client.test.mjs"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_preview_metadata_and_state_creation_rollback_together(tmp_path: Path) -> None:
    import sqlite3
    from datetime import UTC, datetime

    import pytest

    from pastport.adapters.previews import SQLitePreviews
    from pastport.application.player_runtime import PlayerRuntimeError
    from pastport.application.updates import updated

    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        view = client.post(
            f"/api/v1/runs/{run_id}/previews", headers=headers(), json=preview_request(run)
        ).json()
        path = tmp_path / "previews.sqlite3"
        repository = SQLitePreviews(path, "test")
        record = repository.get(settings(tmp_path).accounts[0].actor, run_id, view["preview_id"])
        candidate = updated(record, preview_id="fail-initial-state", request_key="rollback-key")
        state = updated(repository.state(record), release_id="preview:fail-initial-state")
        with sqlite3.connect(path) as connection:
            connection.execute("""CREATE TRIGGER fail_preview_state BEFORE INSERT ON player_saves
                WHEN NEW.save_id='fail-initial-state'
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        with pytest.raises(PlayerRuntimeError) as failure:
            repository.create_preview(candidate, state, datetime.now(UTC))
        assert failure.value.code == "SAVE_STORAGE_FAILED"
        assert (
            repository.find_request(settings(tmp_path).accounts[0].actor, run_id, "rollback-key")
            is None
        )
        assert repository.state(record).revision == 0
