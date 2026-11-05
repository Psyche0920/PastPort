"""Portable startup preserves private accounts and accepts fresh local state."""

import errno
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pastport.api.app import create_app
from pastport.api.settings import Accounts, AppSettings
from pastport.organizer_cli import OrganizerLauncher


def test_fresh_setup_login_and_preserved_identity(tmp_path: Path) -> None:
    launcher = OrganizerLauncher(tmp_path / "path with spaces")
    with patch("getpass.getpass", return_value="local-test-password"):
        launcher.initialize()
    original = launcher.accounts.read_bytes()
    with patch("getpass.getpass", side_effect=AssertionError("Existing account must be retained")):
        launcher.initialize()
    assert launcher.accounts.read_bytes() == original
    accounts = Accounts.model_validate_json(original)
    with patch("socket.socket"):
        arguments = launcher.arguments(18840, None)
    assert str(launcher.accounts) in arguments
    assert "--organizer-player-assets" not in arguments
    app = create_app(
        AppSettings(
            data_directory=launcher.directory / "server",
            accounts=accounts.accounts,
            accounts_file=launcher.accounts,
            evidence_mode="disabled",
            narrative_mode="disabled",
            resources_mode="disabled",
        )
    )
    with TestClient(app, base_url="http://127.0.0.1:18840") as client:
        assert client.get("/organizer/").status_code == 200
        response = client.post(
            "/organizer/api/session",
            json={
                "username": "admin",
                "password": "local-test-password",
            },
            headers={"origin": "http://127.0.0.1:18840", "x-pastport-edit": "1"},
        )
        assert response.status_code == 200
        assert client.get("/organizer/api/jobs").json() == []


def test_missing_setup_has_actionable_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="organizer-init"):
        OrganizerLauncher(tmp_path).arguments(18840, None)


def test_bind_failures_distinguish_port_conflict_from_permission(tmp_path: Path) -> None:
    launcher = OrganizerLauncher(tmp_path)
    with patch("getpass.getpass", return_value="local-test-password"):
        launcher.initialize()
    with patch("socket.socket") as socket:
        socket.return_value.__enter__.return_value.bind.side_effect = OSError(
            errno.EADDRINUSE,
            "Address in use",
        )
        with pytest.raises(ValueError, match="occupied"):
            launcher.arguments(18840, None)
        socket.return_value.__enter__.return_value.bind.side_effect = OSError(
            errno.EACCES,
            "Permission denied",
        )
        with pytest.raises(ValueError, match="Permission denied"):
            launcher.arguments(18840, None)
