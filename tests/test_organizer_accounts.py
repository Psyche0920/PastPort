"""Staff passwords preserve Main permissions and never become frontend API tokens."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_organizer import headers, setup

from pastport.account_cli import AccountPasswordCommand
from pastport.adapters.passwords import PasswordHasher
from pastport.api.app import create_app
from pastport.api.settings import Accounts, Credential

PASSWORD = "Synthetic-staff-password-123"
EDIT = {"X-PastPort-Edit": "1"}


def password_app(root: Path, *, reload_file: bool = False) -> tuple[FastAPI, Path, Credential]:
    settings, production = setup(root)
    original = settings.accounts[0]
    account = Credential.model_validate(
        original.model_dump()
        | {"username": "staff", "password_hash": PasswordHasher().hash(PASSWORD)}
    )
    file = root / "accounts.json"
    file.write_text(Accounts(accounts=(account, settings.accounts[1])).model_dump_json())
    return (
        create_app(
            replace(
                settings,
                accounts=(account, settings.accounts[1]),
                accounts_file=file if reload_file else None,
            ),
            organizer_production=production,
        ),
        file,
        original,
    )


def test_password_login_reuses_actor_and_never_returns_credentials(tmp_path: Path) -> None:
    app, file, original = password_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/organizer/api/session", json={"username": "staff", "password": PASSWORD}, headers=EDIT
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"actor_id": "owner"}
        assert PASSWORD not in response.text
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/organizer/api/jobs").status_code == 200
        assert (
            client.post(
                "/organizer/api/materials",
                headers=EDIT,
                json={"project_id": "elsewhere", "entry_level": "raw"},
            ).status_code
            == 403
        )
        assert client.delete("/organizer/api/session", headers=EDIT).status_code == 204
        assert client.get("/organizer/api/jobs").status_code == 401
        # Developer authentication remains backward compatible.
        assert client.get("/organizer/api/jobs", headers=headers()).status_code == 200


def test_invalid_login_is_generic_and_rate_limited(tmp_path: Path) -> None:
    app, _, _ = password_app(tmp_path)
    with TestClient(app) as client:
        for username in ("staff", "unknown", "staff", "unknown", "staff"):
            response = client.post(
                "/organizer/api/session",
                headers=EDIT,
                json={"username": username, "password": "incorrect"},
            )
            assert response.status_code == 401
            assert response.json()["message"] == "账号或密码不正确。"
        assert (
            client.post(
                "/organizer/api/session",
                headers=EDIT,
                json={"username": "staff", "password": PASSWORD},
            ).status_code
            == 429
        )
    with TestClient(app) as client:
        assert (
            client.post(
                "/organizer/api/session",
                headers={**EDIT, "Origin": "https://untrusted.example"},
                json={"username": "staff", "password": PASSWORD},
            ).status_code
            == 403
        )


def test_local_password_change_reloads_and_invalidates_old_session(tmp_path: Path) -> None:
    app, file, original = password_app(tmp_path, reload_file=True)
    with TestClient(app) as client:
        assert (
            client.post(
                "/organizer/api/session",
                headers=EDIT,
                json={"username": "staff", "password": PASSWORD},
            ).status_code
            == 200
        )
        changed = "Another-synthetic-password-456"
        AccountPasswordCommand().update(file, "owner", " Staff ", changed)
        current = Accounts.model_validate_json(file.read_bytes()).accounts[0]
        assert current.actor == original.actor and current.token_sha256 == original.token_sha256
        assert current.username == "staff"
        assert file.stat().st_mode & 0o777 == 0o600
        assert PASSWORD not in file.read_text() and changed not in file.read_text()
        assert client.get("/organizer/api/jobs").status_code == 401
        assert (
            client.post(
                "/organizer/api/session",
                headers=EDIT,
                json={"username": "staff", "password": PASSWORD},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/organizer/api/session",
                headers=EDIT,
                json={"username": "staff", "password": changed},
            ).status_code
            == 200
        )


def test_salted_hashes_and_invalid_request_do_not_expose_password(tmp_path: Path) -> None:
    hasher = PasswordHasher()
    first = hasher.hash(PASSWORD)
    second = hasher.hash(PASSWORD)
    assert first != second and hasher.verify(PASSWORD, first) and hasher.verify(PASSWORD, second)
    with pytest.raises(ValueError):
        hasher.hash("short")
    app, _, _ = password_app(tmp_path)
    with TestClient(app) as client:
        secret = "sensitive" * 200
        response = client.post(
            "/organizer/api/session", headers=EDIT, json={"username": "staff", "password": secret}
        )
        assert response.status_code == 422
        assert secret not in response.text


def test_single_admin_can_initialize_once_on_local_website(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    account = settings.accounts[0]
    file = tmp_path / "single-admin.json"
    file.write_text(Accounts(accounts=(account,)).model_dump_json())
    app = create_app(
        replace(
            settings, accounts=(account,), accounts_file=file, organizer_local_admin_setup=True
        ),
        organizer_production=production,
    )
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        access = client.get("/organizer/api/access")
        assert access.json() == {"username": "admin", "setup_required": True}
        response = client.post(
            "/organizer/api/admin-setup",
            headers=EDIT,
            json={"password": PASSWORD, "password_confirmation": PASSWORD},
        )
        assert response.status_code == 200, response.text
        assert client.get("/organizer/api/jobs").status_code == 200
        assert client.get("/organizer/api/access").json()["setup_required"] is False
        assert (
            client.post(
                "/organizer/api/admin-setup",
                headers=EDIT,
                json={"password": PASSWORD, "password_confirmation": PASSWORD},
            ).status_code
            == 409
        )
        saved = Accounts.model_validate_json(file.read_bytes())
        assert len(saved.accounts) == 1 and saved.accounts[0].actor == account.actor
        assert saved.accounts[0].username == "admin"
        assert saved.accounts[0].token_sha256 == account.token_sha256
        assert PASSWORD not in file.read_text()
        assert client.delete("/organizer/api/session", headers=EDIT).status_code == 204
        assert (
            client.post(
                "/organizer/api/session",
                headers=EDIT,
                json={"username": "admin", "password": PASSWORD},
            ).status_code
            == 200
        )


def test_single_admin_setup_cannot_be_used_remotely(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    file = tmp_path / "single-admin.json"
    file.write_text(Accounts(accounts=(settings.accounts[0],)).model_dump_json())
    app = create_app(
        replace(
            settings,
            accounts=(settings.accounts[0],),
            accounts_file=file,
            organizer_local_admin_setup=True,
        ),
        organizer_production=production,
    )
    with TestClient(app, base_url="http://127.0.0.1", client=("203.0.113.10", 50000)) as client:
        assert client.get("/organizer/api/access").json()["setup_required"] is False
        assert (
            client.post(
                "/organizer/api/admin-setup",
                headers=EDIT,
                json={"password": PASSWORD, "password_confirmation": PASSWORD},
            ).status_code
            == 403
        )
    assert Accounts.model_validate_json(file.read_bytes()).accounts[0].password_hash is None
