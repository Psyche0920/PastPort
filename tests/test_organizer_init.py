"""A new computer can create its own Organizer administrator without private paths."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

from pastport.api.organizer_accounts import OrganizerAccounts
from pastport.api.settings import Accounts
from pastport.organizer_init import ADMIN_USERNAME, OrganizerAdminInitializer, main

PASSWORD = "Synthetic-admin-password-123"


def test_creates_private_admin_that_the_fixed_login_form_can_use(tmp_path: Path) -> None:
    path = tmp_path / "var/organizer-integration/staff-accounts.json"
    OrganizerAdminInitializer().create(path, PASSWORD)
    accounts = Accounts.model_validate_json(path.read_bytes()).accounts
    assert len(accounts) == 1 and accounts[0].username == ADMIN_USERNAME == "admin"
    assert {"editor", "operator"} <= set(accounts[0].actor.roles)
    assert PASSWORD not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    signed_in = OrganizerAccounts((), path).password("admin", PASSWORD)
    assert signed_in.actor.actor_id == accounts[0].actor.actor_id


def test_never_overwrites_and_rejects_short_passwords(tmp_path: Path) -> None:
    path = tmp_path / "staff-accounts.json"
    with pytest.raises(ValueError):
        OrganizerAdminInitializer().create(path, "short")
    assert not path.exists()
    OrganizerAdminInitializer().create(path, PASSWORD)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        OrganizerAdminInitializer().create(path, "Another-password-456")
    assert path.read_bytes() == before


def test_command_prompts_twice_and_prints_the_portable_start_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "accounts.json"
    answers = iter((PASSWORD, PASSWORD))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    monkeypatch.setattr(sys, "argv", ["organizer-init", "--accounts", str(path)])
    main()
    output = capsys.readouterr().out
    assert "--port 18840" in output and "/Users/" not in output.replace(str(tmp_path), "")
    assert path.is_file()
    mismatched = iter((PASSWORD, PASSWORD + "x"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(mismatched))
    monkeypatch.setattr(sys, "argv", ["organizer-init", "--accounts", str(tmp_path / "other.json")])
    with pytest.raises(SystemExit):
        main()
    assert not (tmp_path / "other.json").exists()


def test_missing_account_file_names_the_setup_command(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pastport", "--accounts", str(tmp_path / "missing.json")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert "missing.json" in result.stderr and "organizer-init" in result.stderr
