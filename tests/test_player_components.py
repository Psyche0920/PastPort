"""Typed preparation components and trusted package bindings used by the F7 runtime."""

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_package_loader import FIXTURES, package_loader, reference

from pastport.adapters.player_process import NodePlayerProcess, PlayerComponentError
from pastport.application.player_components import PlayerComponents
from pastport.application.player_preparation import PlayerComponentCommand
from pastport.application.updates import updated
from pastport.domain.game import ActionRequest, PlayerState
from pastport.domain.package_loading import PackageLoadError


def components(node_path: Path | None = None) -> PlayerComponents:
    return PlayerComponents(
        (FIXTURES / "runtime.json").read_bytes(),
        reference(),
        "release-test-1",
        package_loader(),
        NodePlayerProcess(node_path),
    )


def observe(state: PlayerState, **changes: object) -> ActionRequest:
    payload: dict[str, object] = {
        "project_id": state.project_id,
        "release_id": state.release_id,
        "package_hash": state.package_hash,
        "action": {
            "kind": "observe",
            "action_id": "observe-1",
            "expected_revision": 0,
            "target_id": "inspect-hatch",
            "spot_id": "hatch",
        },
    }
    payload.update(changes)
    return ActionRequest.model_validate(payload)


def test_real_js_initial_state_matches_shared_fixture_and_is_not_saved() -> None:
    player = components()
    state = player.initial_state()
    assert state == PlayerState.model_validate_json((FIXTURES / "player-state.json").read_bytes())
    player.validate_state(state)
    assert player.initial_state() == state


def test_observation_proposal_then_single_rule_and_effect_are_explicitly_uncommitted() -> None:
    player = components()
    state = player.initial_state()
    result = player.propose_action(state, observe(state))
    assert not result.committed and result.status == "prepared"
    assert result.state.completed_task_ids == ("inspect-hatch",)
    assert tuple(event.kind for event in result.emitted_events) == (
        "spot_observed",
        "task_completed",
    )
    assert result.state.revision == 0 and result.state.processed_actions == ()
    assert result.state.inventory == () and state.observations == ()
    rules = player.match_rules(result.state, result.emitted_events[1])
    assert rules.matched_rules
    effect = rules.matched_rules[0].effects[0]
    effect_result = player.evaluate_effect(result.state, effect)
    assert "delivery-note" in effect_result.state.inventory
    assert effect_result.state.applied_rule_keys == ()
    assert player.propose_action(result.state, observe(state)).emitted_events == ()


@pytest.mark.parametrize(
    "field,value", [("release_id", "other-release"), ("package_hash", "0" * 64)]
)
def test_action_and_state_identity_rejected(field: str, value: str) -> None:
    player = components()
    state = player.initial_state()
    with pytest.raises(PlayerComponentError, match="another package or release"):
        player.propose_action(state, observe(state, **{field: value}))
    with pytest.raises(PlayerComponentError) as failure:
        player.validate_state(updated(state, **{field: value}))
    assert failure.value.code == "PLAYER_IDENTITY_MISMATCH"


def test_forged_completed_task_and_scalar_type_are_rejected() -> None:
    player = components()
    state = player.initial_state()
    with pytest.raises(PlayerComponentError) as failure:
        player.validate_state(updated(state, completed_task_ids=("inspect-hatch",)))
    assert failure.value.code == "PLAYER_STATE_INVALID"
    with pytest.raises(PlayerComponentError):
        player.validate_state(updated(state, variables=(updated(state.variables[0], value=0),)))


def test_package_tampering_fails_before_any_process_call() -> None:
    with pytest.raises(PackageLoadError) as failure:
        PlayerComponents(
            (FIXTURES / "runtime.json").read_bytes(),
            updated(reference(), sha256="0" * 64),
            "release-test-1",
            package_loader(),
            NodePlayerProcess(Path("/missing/node")),
        )
    assert failure.value.code == "RUNTIME_HASH_MISMATCH"


def test_missing_node_and_invalid_transport_have_safe_errors() -> None:
    with pytest.raises(PlayerComponentError) as failure:
        components(Path("/missing/node")).initial_state()
    assert failure.value.code == "PLAYER_PROCESS_UNAVAILABLE"
    command = PlayerComponentCommand(
        operation="initialize",
        package=components().package,
        reference=reference(),
        release_id="release-test-1",
    )
    with pytest.raises(PlayerComponentError) as failure:
        NodePlayerProcess(Path("/usr/bin/true")).execute(command)
    assert failure.value.code == "PLAYER_RESPONSE_INVALID"
    with pytest.raises(ValidationError):
        updated(command, operation="propose_action")


def test_generated_player_contracts_are_current() -> None:
    from pastport.development.player_contracts import generated

    root = Path(__file__).resolve().parents[1] / "src" / "pastport" / "player"
    for name, content in generated().items():
        assert (root / name).read_text() == content


def test_javascript_components() -> None:
    result = subprocess.run(
        [
            "node",
            "--test",
            "tests/player-components.test.mjs",
            "tests/player-runtime.test.mjs",
            "tests/game/*.test.mjs",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_action_fixture_metadata_stays_declarative() -> None:
    vectors = sorted(FIXTURES.glob("vector-*.json"))
    assert len(vectors) == 5
    assert all(json.loads(path.read_text())["evaluation_status"] == "not_run" for path in vectors)


def test_private_initial_state_requires_authorized_valid_release(tmp_path: Path) -> None:
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

    path = "/api/v1/projects/project-1/player-initial-state"
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get(path).status_code == 401
        run_id = create_run(client)
        assert client.get(path, headers=headers(token=RESTRICTED_TOKEN)).status_code == 403
        assert client.get(path, headers=headers()).status_code == 404
        confirm_direction(client, run_id)
        for _ in range(3):
            approve_gate(client, run_id)
        run = wait_for(client, run_id, "published")
        result = client.get(path, headers=headers())
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["committed"] is False and body["can_commit_actions"] is True
        assert body["can_persist"] is True
        assert body["state"]["release_id"] == run.current_release_id
        assert run.state.runtime_ref is not None
        assert body["state"]["package_hash"] == run.state.runtime_ref.sha256
        assert client.get(path, headers=headers()).json() == body
        package = tmp_path / "releases" / "project-1" / str(run.current_release_id) / "package.json"
        package.write_text("{}")
        assert client.get(path, headers=headers()).status_code == 404


def test_node_process_timeout_is_bounded_and_reaped(tmp_path: Path) -> None:
    import sys

    executable = tmp_path / "slow-node"
    executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
    executable.chmod(0o700)
    command = PlayerComponentCommand(
        operation="initialize",
        package=components().package,
        reference=reference(),
        release_id="release-test-1",
    )
    with pytest.raises(PlayerComponentError) as failure:
        NodePlayerProcess(executable, timeout_seconds=0.05).execute(command)
    assert failure.value.code == "PLAYER_TIMEOUT"
