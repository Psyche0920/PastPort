"""Shared packages: chunked upload, immutable versions, conflicts, restore and publish CAS."""

import hashlib
import io
import json
import random
import sqlite3
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_organizer import Production

from pastport.adapters.organizer_packages import CHUNK_BYTES
from pastport.api.app import create_app
from pastport.api.settings import AppSettings, Credential
from pastport.application.models import Actor
from pastport.organizer_data import DataIdentity, DataIdentityError, DeploymentBackup

TOKEN = "packages-test-only-token"


def archive(label: str, padding: int = 0) -> bytes:
    """A minimal static delivery named `trial`, distinct per label."""
    buffer = io.BytesIO()
    files = {
        "trial/index.html": b"Static transport fixture",
        "trial/prototype/adventure.html": f"<html>{label}</html>".encode(),
        "trial/assets/noise.bin": random.Random(label).randbytes(padding),
        "trial/authoring/story.mjs": f"export const label={label!r};".encode(),
        "trial/pastport-player.json": json.dumps(
            {"format": "pastport-static-v1", "entrypoint": "prototype/adventure.html"}
        ).encode(),
    }
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=1) as stream:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            stream.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = AppSettings(
        data_directory=tmp_path / "server",
        evidence_mode="disabled",
        narrative_mode="disabled",
        resources_mode="disabled",
        accounts=(
            Credential(
                token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
                actor=Actor(actor_id="admin", roles=("editor", "operator"), project_ids=None),
            ),
            Credential(
                token_sha256=hashlib.sha256(b"stranger").hexdigest(),
                actor=Actor(actor_id="stranger", roles=("editor", "operator"), project_ids=None),
            ),
        ),
    )
    with TestClient(create_app(settings, organizer_production=Production())) as value:
        yield value


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def upload(
    client: TestClient, content: bytes, base: str | None = None, note: str = ""
) -> dict[str, Any]:
    start = client.post(
        "/organizer/api/delivery-uploads",
        json={"filename": "trial.tar.gz", "size": len(content)},
        headers=auth(),
    )
    assert start.status_code == 201, start.text
    state = start.json()
    offset = 0
    while offset < len(content):
        chunk = content[offset : offset + state["chunk_bytes"]]
        response = client.put(
            f"/organizer/api/delivery-uploads/{state['upload_id']}?offset={offset}",
            content=chunk,
            headers=auth(),
        )
        assert response.status_code == 200, response.text
        offset = response.json()["received"]
    response = client.post(
        f"/organizer/api/delivery-uploads/{state['upload_id']}/import",
        json={"base_job_id": base, "note": note},
        headers=auth(),
    )
    return {**response.json(), "http": response.status_code}


def test_versions_are_shared_immutable_and_refuse_stale_bases(client: TestClient) -> None:
    first = upload(client, archive("v1"))
    assert first["http"] == 201 and first["delivery"]["created"]
    repeat = upload(client, archive("v1"))
    assert repeat["http"] == 201 and not repeat["delivery"]["created"]
    assert repeat["job_id"] == first["job_id"]
    unnamed = upload(client, archive("other"))
    assert unnamed["http"] == 409 and unnamed["code"] == "DELIVERY_NAME_EXISTS"
    second = upload(client, archive("v2"), base=first["job_id"], note="fixed copy")
    assert second["http"] == 201
    # Another member still holding version 1 cannot replace version 2 silently.
    stale = upload(client, archive("v2-elsewhere"), base=first["job_id"])
    assert stale["http"] == 409 and stale["code"] == "DELIVERY_VERSION_CONFLICT"
    [package] = client.get("/organizer/api/packages", headers=auth()).json()
    assert package["current_job_id"] == second["job_id"]
    assert [v["number"] for v in package["versions"]] == [1, 2]
    assert package["versions"][1]["parent_job_id"] == first["job_id"]
    assert package["versions"][1]["note"] == "fixed copy"
    assert client.get("/organizer/api/packages", headers=auth("stranger")).json() == []
    restored = client.post(
        f"/organizer/api/packages/{package['package_id']}/restore",
        json={"job_id": first["job_id"], "expected_revision": package["revision"]},
        headers=auth(),
    )
    assert restored.status_code == 200 and restored.json()["current_job_id"] == first["job_id"]
    again = client.post(
        f"/organizer/api/packages/{package['package_id']}/restore",
        json={"job_id": second["job_id"], "expected_revision": package["revision"]},
        headers=auth(),
    )
    assert again.status_code == 409
    forbidden = client.post(
        f"/organizer/api/packages/{package['package_id']}/restore",
        json={"job_id": second["job_id"], "expected_revision": restored.json()["revision"]},
        headers=auth("stranger"),
    )
    assert forbidden.status_code == 403


def test_download_returns_reimportable_archive_and_lists_missing_materials(
    client: TestClient,
) -> None:
    content = archive("v1")
    first = upload(client, content)
    response = client.get(f"/organizer/api/jobs/{first['job_id']}/download", headers=auth())
    assert response.status_code == 200 and response.content == content
    assert 'filename="trial.tar.gz"' in response.headers["content-disposition"]
    assert (
        client.get(f"/organizer/api/jobs/{first['job_id']}/download", headers=auth("stranger"))
    ).status_code == 403
    materials = client.get(f"/organizer/api/jobs/{first['job_id']}/materials", headers=auth())
    items = {item["label"]: item for item in materials.json()["items"]}
    assert items["包内可编辑源文件"]["available"]
    assert "authoring/story.mjs" in items["包内可编辑源文件"]["detail"]
    assert not items["原始史料与现场照片"]["available"]


def test_chunks_resume_after_a_repeat_and_refuse_gaps_or_oversize(client: TestClient) -> None:
    content = archive("big", padding=CHUNK_BYTES + 1000)
    start = client.post(
        "/organizer/api/delivery-uploads",
        json={"filename": "trial.tar.gz", "size": len(content)},
        headers=auth(),
    ).json()
    base = f"/organizer/api/delivery-uploads/{start['upload_id']}"
    gap = client.put(base + "?offset=10", content=content[10:20], headers=auth())
    assert gap.status_code == 409
    first = client.put(base + "?offset=0", content=content[:CHUNK_BYTES], headers=auth())
    assert first.json()["received"] == min(CHUNK_BYTES, len(content))
    # A retried chunk (response lost) is acknowledged without rewriting confirmed bytes.
    retry = client.put(base + "?offset=0", content=content[:CHUNK_BYTES], headers=auth())
    assert retry.json()["received"] == first.json()["received"]
    early = client.post(base + "/import", json={}, headers=auth())
    assert early.status_code == 409
    rest = client.put(f"{base}?offset={CHUNK_BYTES}", content=content[CHUNK_BYTES:], headers=auth())
    assert rest.json()["received"] == len(content)
    over = client.put(f"{base}?offset={len(content)}", content=b"x", headers=auth())
    assert over.status_code == 413
    other = client.post(base + "/import", json={}, headers=auth("stranger"))
    assert other.status_code == 404
    done = client.post(base + "/import", json={}, headers=auth())
    assert done.status_code == 201


def test_publish_records_history_and_refuses_a_stale_expected_version(client: TestClient) -> None:
    first = upload(client, archive("v1"))
    second = upload(client, archive("v2"), base=first["job_id"])
    url = "/organizer/api/jobs/{}/publish-to-map"
    one = client.post(
        url.format(first["job_id"]),
        json={"site_id": "muradiye", "expected_version": "none"},
        headers=auth(),
    )
    assert one.status_code == 200, one.text
    stale = client.post(
        url.format(second["job_id"]),
        json={"site_id": "muradiye", "expected_version": "none"},
        headers=auth(),
    )
    assert stale.status_code == 409
    two = client.post(
        url.format(second["job_id"]),
        json={"site_id": "muradiye", "expected_version": one.json()["version"]},
        headers=auth(),
    )
    assert two.status_code == 200
    back = client.post(
        url.format(first["job_id"]),
        json={"site_id": "muradiye", "expected_version": two.json()["version"]},
        headers=auth(),
    )
    assert back.status_code == 200 and back.json()["version"] == one.json()["version"]
    states = client.get("/organizer/api/map-publications", headers=auth()).json()
    [state] = [item for item in states if item["site_id"] == "muradiye"]
    assert state["current"]["job_id"] == first["job_id"]
    assert [entry["job_id"] for entry in state["history"]] == [
        first["job_id"],
        second["job_id"],
        first["job_id"],
    ]


def test_known_store_is_never_replaced_by_an_empty_one(tmp_path: Path) -> None:
    identity = DataIdentity(tmp_path)
    created = identity.verify()
    assert identity.verify() == created
    (tmp_path / "server/organizer/.pastport-data-id").unlink()
    with pytest.raises(DataIdentityError, match="No empty store"):
        identity.verify()
    assert not (tmp_path / "server/organizer/.pastport-data-id").exists()


def test_backup_copies_databases_and_games_without_upload_staging(tmp_path: Path) -> None:
    directory = tmp_path / "deployment"
    DataIdentity(directory).verify()
    store = directory / "server/organizer"
    with sqlite3.connect(store / "organizer.sqlite3") as database:
        database.execute("CREATE TABLE records (kind TEXT, id TEXT, payload TEXT)")
        database.execute("INSERT INTO records VALUES ('job','a','{}')")
    (store / "jobs/a/game-3d").mkdir(parents=True)
    (store / "jobs/a/game-3d/index.html").write_text("game")
    (store / "delivery-uploads").mkdir()
    (store / "delivery-uploads/partial").write_text("x")
    players = tmp_path / "players"
    players.mkdir()
    with sqlite3.connect(players / "players.sqlite") as database:
        database.execute("CREATE TABLE player (id TEXT)")
        database.execute("CREATE TABLE stamp (player TEXT)")
        database.execute("INSERT INTO player VALUES ('p')")
    output = tmp_path / "backup"
    summary = DeploymentBackup(directory, players).create(output)
    assert summary["organizer_records"] == {"job": 1}
    assert summary["player_rows"] == {"player": 1, "stamp": 0}
    assert (output / "server/organizer/jobs/a/game-3d/index.html").read_text() == "game"
    assert not (output / "server/organizer/delivery-uploads").exists()
    assert DataIdentity(output).verify() == DataIdentity(directory).verify()
    with pytest.raises(ValueError, match="already exists"):
        DeploymentBackup(directory, players).create(output)
