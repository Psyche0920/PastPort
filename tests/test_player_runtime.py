"""Real JS, durable SQLite CAS, crash recovery and private HTTP session isolation."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_package_loader import FIXTURES, package_loader, reference
from test_player_components import observe
from test_service import (
    RESTRICTED_TOKEN,
    approve_gate,
    confirm_direction,
    create_run,
    headers,
    settings,
    wait_for,
)

from pastport.adapters.player_process import NodePlayerProcess, PlayerComponentError
from pastport.adapters.player_saves import SQLitePlayerSaves
from pastport.api.app import create_app
from pastport.application.player_runtime import PlayerRuntimeError, SharedPlayerRuntime
from pastport.application.player_service import PlayerService
from pastport.application.updates import updated
from pastport.domain.common import CanonicalSerializer
from pastport.domain.game import ActionRequest, PlayerState
from pastport.domain.player_saves import PlayerSaveKey
from pastport.ports.modules import PlayerRuntimePort


def runtime(release_id: str = "release-test-1") -> SharedPlayerRuntime:
    return SharedPlayerRuntime(
        (FIXTURES / "runtime.json").read_bytes(),
        reference(),
        release_id,
        package_loader(),
        NodePlayerProcess(),
    )


def key(**changes: str) -> PlayerSaveKey:
    return PlayerSaveKey.model_validate(
        {
            "environment": "test",
            "actor_id": "player-a",
            "project_id": "fixture-project",
            "save_id": "slot-1",
            **changes,
        }
    )


def service(path: Path, release_id: str = "release-test-1") -> PlayerService:
    engine = runtime(release_id)
    return PlayerService(SQLitePlayerSaves(path), engine, engine.package, release_id)


def choice(state: PlayerState) -> ActionRequest:
    return ActionRequest.model_validate(
        {
            "project_id": state.project_id,
            "release_id": state.release_id,
            "package_hash": state.package_hash,
            "action": {
                "action_id": "choose-help",
                "kind": "choose",
                "expected_revision": state.revision,
                "target_id": "witness-choice",
                "option_id": "help",
            },
        }
    )


def test_shared_runtime_implements_the_frozen_port_and_returns_typed_results() -> None:
    engine = runtime()
    port: PlayerRuntimePort = engine
    state = port.initial_state(engine.package, engine.release_id)
    result = port.apply_action(engine.package, state, observe(state))
    assert result.state.revision == 1
    assert result.state.processed_actions[0].payload_hash == CanonicalSerializer.digest(
        observe(state).action
    )
    port.validate_state(engine.package, result.state)
    with pytest.raises(PlayerRuntimeError):
        port.initial_state(engine.package, "wrong-release")


def test_restart_restores_once_keys_and_late_replay_returns_latest_state(tmp_path: Path) -> None:
    path = tmp_path / "player.sqlite3"
    player = service(path)
    initial = player.create(key())
    seen = player.apply(key(), observe(initial)).state
    assert seen.inventory == ("delivery-note",)
    resumed = service(path)
    assert resumed.load(key()) == seen
    chosen = resumed.apply(key(), choice(seen)).state
    assert chosen.elapsed_minutes == 2
    retry = service(path).apply(key(), observe(initial))
    assert retry.state == chosen and retry.emitted_events == () and retry.trace == ()
    assert retry.feedback_keys == ("observe-feedback",)
    assert service(path).create(key()) == chosen
    assert service(path).load(key()).applied_rule_keys == ("once:assist-witness", "once:grant-note")


def test_owner_environment_release_and_project_cannot_overwrite_another_save(
    tmp_path: Path,
) -> None:
    path = tmp_path / "player.sqlite3"
    player = service(path)
    initial = player.create(key())
    current = player.apply(key(), observe(initial)).state
    for changed in [key(actor_id="player-b"), key(environment="production")]:
        with pytest.raises(PlayerRuntimeError) as failure:
            player.load(changed)
        assert failure.value.code == "SAVE_NOT_FOUND"
        assert player.create(changed).revision == 0
    with pytest.raises(PlayerRuntimeError) as failure:
        player.create(key(project_id="other-project"))
    assert failure.value.code == "SAVE_IDENTITY_MISMATCH"
    newer = service(path, "release-test-2")
    for operation in (newer.load, newer.create):
        with pytest.raises(PlayerRuntimeError) as failure:
            operation(key())
        assert failure.value.code == "SAVE_IDENTITY_MISMATCH"
    assert player.load(key()) == current


class RacingRepository:
    def __init__(self, path: Path) -> None:
        self.delegate = SQLitePlayerSaves(path)
        self.barrier = Barrier(2)

    def create(self, key: PlayerSaveKey, state: PlayerState) -> PlayerState:
        return self.delegate.create(key, state)

    def load(self, key: PlayerSaveKey) -> PlayerState | None:
        return self.delegate.load(key)

    def compare_and_swap(
        self, key: PlayerSaveKey, previous: PlayerState, following: PlayerState
    ) -> bool:
        self.barrier.wait(timeout=10)
        return self.delegate.compare_and_swap(key, previous, following)


@pytest.mark.parametrize("same_action", [True, False])
def test_concurrent_identical_retry_or_different_stale_action_never_loses_updates(
    tmp_path: Path, same_action: bool
) -> None:
    path = tmp_path / "player.sqlite3"
    initial = service(path).create(key())
    repository = RacingRepository(path)
    engine = runtime()
    player = PlayerService(repository, engine, engine.package, engine.release_id)
    first = observe(initial)
    second = (
        first
        if same_action
        else updated(first, action=updated(first.action, action_id="observe-other"))
    )

    def apply(action: ActionRequest) -> PlayerState | str:
        try:
            return player.apply(key(), action).state
        except PlayerComponentError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, [first, second]))
    stored = service(path).load(key())
    assert stored.revision == 1 and len(stored.processed_actions) == 1
    if same_action:
        assert results == [stored, stored]
    else:
        assert results.count("STATE_STALE") == 1 and stored in results


class FailedCommitRepository:
    def __init__(self, path: Path) -> None:
        self.delegate = SQLitePlayerSaves(path)

    def create(self, key: PlayerSaveKey, state: PlayerState) -> PlayerState:
        return self.delegate.create(key, state)

    def load(self, key: PlayerSaveKey) -> PlayerState | None:
        return self.delegate.load(key)

    def compare_and_swap(
        self, key: PlayerSaveKey, previous: PlayerState, following: PlayerState
    ) -> bool:
        raise PlayerRuntimeError("SAVE_STORAGE_FAILED", "Injected write failure")


def test_storage_failure_keeps_last_committed_state_and_retry_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "player.sqlite3"
    initial = service(path).create(key())
    engine = runtime()
    broken = PlayerService(FailedCommitRepository(path), engine, engine.package, engine.release_id)
    with pytest.raises(PlayerRuntimeError, match="Injected write failure"):
        broken.apply(key(), observe(initial))
    assert service(path).load(key()) == initial
    assert service(path).apply(key(), observe(initial)).state.revision == 1


def test_actual_process_exit_before_commit_rolls_back_and_after_commit_replays_receipt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "player.sqlite3"
    initial = service(path).create(key())
    before = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1], isolation_level=None)
connection.execute('BEGIN IMMEDIATE')
connection.execute(
    "UPDATE player_saves SET state_json='broken-uncommitted' WHERE save_id=?", ('slot-1',)
)
os._exit(23)
""",
            str(path),
        ],
        check=False,
        timeout=10,
    )
    assert before.returncode == 23 and service(path).load(key()) == initial
    engine = runtime()
    following = engine.apply_action(engine.package, initial, observe(initial)).state
    old_file, new_file, key_file = (
        tmp_path / name for name in ["old.json", "new.json", "key.json"]
    )
    old_file.write_text(initial.model_dump_json())
    new_file.write_text(following.model_dump_json())
    key_file.write_text(key().model_dump_json())
    after = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os, sys
from pathlib import Path
from pastport.adapters.player_saves import SQLitePlayerSaves
from pastport.domain.game import PlayerState
from pastport.domain.player_saves import PlayerSaveKey
repository = SQLitePlayerSaves(Path(sys.argv[1]))
previous = PlayerState.model_validate_json(Path(sys.argv[2]).read_bytes())
following = PlayerState.model_validate_json(Path(sys.argv[3]).read_bytes())
key = PlayerSaveKey.model_validate_json(Path(sys.argv[4]).read_bytes())
assert repository.compare_and_swap(key, previous, following)
os._exit(23)
""",
            str(path),
            str(old_file),
            str(new_file),
            str(key_file),
        ],
        check=False,
        timeout=10,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert after.returncode == 23
    retry = service(path).apply(key(), observe(initial))
    assert retry.state == following and retry.emitted_events == ()
    assert retry.state.revision == 1


def test_corrupt_state_and_unknown_storage_version_are_refused_without_reset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "player.sqlite3"
    player = service(path)
    initial = player.create(key())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE player_saves SET state_json=?",
            (updated(initial, revision=1).model_dump_json(),),
        )
    with pytest.raises(PlayerRuntimeError) as failure:
        player.load(key())
    assert failure.value.code == "SAVE_CORRUPT"
    with pytest.raises(PlayerRuntimeError):
        player.create(key())
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(PlayerRuntimeError) as failure:
        SQLitePlayerSaves(path)
    assert failure.value.code == "SAVE_VERSION_UNSUPPORTED"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM player_saves").fetchone()[0] == 1


def test_private_http_saves_resume_and_reject_state_patches_unauthorized_and_stale_actions(
    tmp_path: Path,
) -> None:
    configuration = settings(tmp_path)
    base = "/api/v1/projects/project-1/player-saves"
    with TestClient(create_app(configuration)) as client:
        assert client.post(base, json={"save_id": "slot"}).status_code == 401
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        wait_for(client, run_id, "published")
        assert (
            client.post(base, headers=headers(), json={"save_id": "slot", "state": {}}).status_code
            == 422
        )
        result = client.post(base, headers=headers(), json={"save_id": "slot"})
        assert result.status_code == 200, result.text
        initial = PlayerState.model_validate_json(json.dumps(result.json()["state"]))
        request = observe(initial)
        seen = client.post(
            base + "/slot/actions", headers=headers(), json=request.model_dump(mode="json")
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["persisted"] is True
        expected = seen.json()["result"]["state"]
        assert (
            client.get(base + "/slot", headers=headers(token=RESTRICTED_TOKEN)).status_code == 403
        )
        assert client.get(base + "/missing", headers=headers()).status_code == 404
    with TestClient(create_app(configuration)) as client:
        assert client.get(base + "/slot", headers=headers()).json()["state"] == expected
        replay = client.post(
            base + "/slot/actions", headers=headers(), json=request.model_dump(mode="json")
        )
        assert replay.json()["result"]["state"] == expected
        assert replay.json()["result"]["emitted_events"] == []
        stale = updated(request, action=updated(request.action, action_id="different"))
        error = client.post(
            base + "/slot/actions", headers=headers(), json=stale.model_dump(mode="json")
        )
        assert error.status_code == 409 and error.json()["code"] == "STATE_STALE"
        mismatch = updated(request, package_hash="0" * 64)
        error = client.post(
            base + "/slot/actions", headers=headers(), json=mismatch.model_dump(mode="json")
        )
        assert error.status_code == 409 and error.json()["code"] == "PLAYER_IDENTITY_MISMATCH"
        assert client.get(base + "/slot", headers=headers()).json()["state"] == expected


def test_unrecognized_database_is_never_rebuilt_as_player_storage(tmp_path: Path) -> None:
    path = tmp_path / "authoritative.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE reviews (decision TEXT NOT NULL)")
        connection.execute("INSERT INTO reviews VALUES (?)", ("approved",))
    with pytest.raises(PlayerRuntimeError) as failure:
        SQLitePlayerSaves(path)
    assert failure.value.code == "SAVE_VERSION_UNSUPPORTED"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT decision FROM reviews").fetchone()[0] == "approved"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0


def test_same_project_accounts_have_separate_private_save_namespaces(tmp_path: Path) -> None:
    import hashlib
    from dataclasses import replace

    from pastport.api.settings import Credential
    from pastport.application.models import Actor

    token = "another-local-test-player-token-longer-than-32-characters"
    configuration = settings(tmp_path)
    configuration = replace(
        configuration,
        accounts=configuration.accounts
        + (
            Credential(
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                actor=Actor(actor_id="other-player", roles=("editor",), project_ids=("project-1",)),
            ),
        ),
    )
    base = "/api/v1/projects/project-1/player-saves"
    with TestClient(create_app(configuration)) as client:
        run_id = create_run(client)
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        wait_for(client, run_id, "published")
        original = client.post(base, headers=headers(), json={"save_id": "slot"})
        state = PlayerState.model_validate_json(json.dumps(original.json()["state"]))
        assert (
            client.post(
                base + "/slot/actions",
                headers=headers(),
                json=observe(state).model_dump(mode="json"),
            ).status_code
            == 200
        )
        assert client.get(base + "/slot", headers=headers(token=token)).status_code == 404
        other = client.post(base, headers=headers(token=token), json={"save_id": "slot"})
        assert other.status_code == 200 and other.json()["state"]["revision"] == 0
        assert client.get(base + "/slot", headers=headers()).json()["state"]["revision"] == 1
