"""Native audit writes, ownership, stale snapshots and Story-before-review gating."""

import base64
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_organizer import Production, await_job, headers, setup

from pastport.adapters.organizer_review import SDKOrganizerReview
from pastport.api.app import create_app
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import OrganizerCatalog, OrganizerStart
from pastport.domain.organizer_review import OrganizerReviewBinding


def review_app(tmp_path: Path) -> tuple[FastAPI, Production, Path, Path, SDKOrganizerReview]:
    from importlib.resources import files

    from pastport_matched_environment.application.vr_content import VRContentService

    settings, _ = setup(tmp_path)
    root = tmp_path / "native"
    (root / "media").mkdir(parents=True)
    (root / "vr_trial").mkdir()
    (root / "import-manifest.json").write_text('{"fixture":"review-only"}')
    (root / "source.pdf").write_bytes(b"%PDF-synthetic-mapping")
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/x8AAwMCAO+aX1cAAAAASUVORK5CYII="
    )
    (root / "media/photo.png").write_bytes(image)
    (root / "media/history.png").write_bytes(image)
    schema = Path(
        str(files("pastport_matched_environment").joinpath("reference_environment/schema.sql"))
    ).read_text()
    database = root / "pastport_matching.sqlite3"
    with sqlite3.connect(database) as db:
        db.executescript(schema)
        db.execute("ALTER TABLE modern_objects ADD COLUMN stable_id TEXT")
        db.execute(
            "INSERT INTO buildings VALUES('fixture-building','Synthetic building','Test evidence')"
        )
        db.execute(
            (
                "INSERT INTO source_pages VALUES(1,1,'Synthetic evidence','Sy"
                "nthetic evidence',?,'text')"
            ),
            ("a" * 64,),
        )
        db.execute(
            "INSERT INTO modern_objects VALUES(1,'Synthetic hatch','test'"
            ",'Test only',NULL,'stable-one')"
        )
        db.execute(
            "INSERT INTO historical_objects VALUES('fixture-building/memb"
            "er','fixture-building',NULL,'历史测试对象','Synthetic object',1,'["
            "]','media/history.png','test','Synthetic fixture only')"
        )
        db.execute("INSERT INTO passages VALUES(1,1,0,18,'Synthetic evidence','','')")
        db.execute(
            "INSERT INTO text_associations VALUES('fixture-building/membe"
            "r',1,'测试证据','direct','Synthetic only','fixture','unreviewed'"
            ")"
        )
        db.execute(
            "INSERT INTO pairings VALUES(1,'fixture-building/member','can"
            "didate_unreviewed','Synthetic rationale','test',NULL,NULL,'u"
            "nreviewed','unreviewed',0)"
        )
        db.execute(
            "INSERT INTO photos VALUES(1,'photo.png','media/photo.png','fixture-only',1,1,?)",
            ("b" * 64,),
        )
        db.execute(
            "INSERT INTO observations VALUES(1,1,1,0,0,1,1,'candidate','Test only','fixture')"
        )
    (root / "vr_trial/index.html").write_text(
        '<script id="tour-data" type="application/json">'
        + json.dumps(
            {
                "scenes": [
                    {
                        "hotspots": [
                            {"id": "trial-object-1", "text": "Synthetic initial introduction"}
                        ]
                    }
                ]
            }
        )
        + "</script>"
    )
    VRContentService(database).initialize()
    binding = root / "review-binding.json"
    binding.write_text(
        OrganizerReviewBinding(
            root=root,
            worlds=(root / "one", root / "two"),
            import_sha256=hashlib.sha256((root / "import-manifest.json").read_bytes()).hexdigest(),
        ).model_dump_json()
    )
    assert settings.organizer_catalog is not None
    catalog = OrganizerCatalog.model_validate_json(settings.organizer_catalog.read_bytes())
    source = catalog.sources[0].model_copy(update={"review_binding_file": binding})
    settings.organizer_catalog.write_text(OrganizerCatalog(sources=(source,)).model_dump_json())

    class ReviewProduction(Production):
        async def run(
            self,
            request: GameMakingRequest,
            start: OrganizerStart,
            output: Path,
            *,
            resume: bool = False,
        ) -> None:
            if start.stop_after == "story":
                self.calls.append((start.mode, resume))
                (output / "organizer-production-request.json").write_text(
                    request.model_copy(update={"output_directory": output}).model_dump_json()
                )
                return
            await super().run(request, start, output, resume=resume)

    production = ReviewProduction()
    gateway = SDKOrganizerReview(include_spatial=False)
    return (
        create_app(settings, organizer_production=production, organizer_reviews=gateway),
        production,
        database,
        root,
        gateway,
    )


def test_native_review_is_private_and_hands_off_without_extra_confirmation(tmp_path: Path) -> None:
    app, production, database, root, _ = review_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/organizer/api/review/fixture").status_code == 401
        assert (
            client.get(
                "/organizer/api/review/fixture", headers={"Authorization": "Bearer outsider"}
            ).status_code
            == 403
        )
        view = client.get("/organizer/api/review/fixture", headers=headers()).json()
        assert view["snapshot_current"] is True
        assert view["database_path"] == str(database.resolve())
        assert len(view["objects"]) == 1
        assert view["objects"][0]["photos"]
        body = {"source_id": "fixture", "mode": "reuse", "stop_after": "story"}
        response = client.post("/organizer/api/jobs", headers=headers(), json=body)
        assert response.status_code == 202, response.text
        assert await_job(client, response.json()["job_id"])["status"] == "story_ready"
        assert production.calls == [("reuse", False)]
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT image_review,text_review FROM pairings").fetchone() == (
                "unreviewed",
                "unreviewed",
            )


def test_edits_use_same_native_audit_and_stale_versions_never_overwrite(tmp_path: Path) -> None:
    app, production, database, _, _ = review_app(tmp_path)
    with TestClient(app) as client:
        url = "/organizer/api/review/fixture/objects/1"
        body = {
            "kind": "review",
            "expected_version": 0,
            "image": "suitable",
            "text": "context_only",
            "note": "Specific fixture review",
        }
        response = client.post(url, headers=headers(), json=body)
        assert response.status_code == 200, response.text
        view = response.json()
        assert not view["snapshot_current"]
        assert view["objects"][0]["history"][0]["reviewer"] == "owner"
        assert client.post(url, headers=headers(), json=body).status_code == 409
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT count(*) FROM review_events").fetchone() == (1,)
            assert db.execute(
                "SELECT image_review,text_review,version FROM pairings"
            ).fetchone() == ("suitable", "context_only", 1)
        response = client.post(
            "/organizer/api/jobs",
            headers=headers(),
            json={
                "source_id": "fixture",
                "mode": "regenerate",
                "authorize_model": True,
                "stop_after": "story",
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == "REVIEW_SNAPSHOT_STALE"
        assert not production.calls
        body = {
            "kind": "introduction",
            "expected_version": 0,
            "content": "Human fixture introduction",
        }
        assert client.post(url, headers=headers(), json=body).status_code == 200
        assert client.post(url, headers=headers(), json=body).status_code == 409
        with sqlite3.connect(database) as db:
            assert db.execute(
                "SELECT human_override,version FROM vr_display_contents"
            ).fetchone() == ("Human fixture introduction", 1)
            assert db.execute("SELECT count(*) FROM vr_content_events").fetchone() == (1,)


def test_media_only_exposes_registered_assets(tmp_path: Path) -> None:
    app, _, _, _, _ = review_app(tmp_path)
    with TestClient(app) as client:
        view = client.get("/organizer/api/review/fixture", headers=headers()).json()
        key = view["objects"][0]["photos"][0]["asset_id"]
        assert (
            client.get("/organizer/api/review/fixture/media/" + key, headers=headers()).status_code
            == 200
        )
        assert client.get("/organizer/api/review/fixture/media/" + key).status_code == 401
        assert (
            client.get(
                "/organizer/api/review/fixture/media/not-registered", headers=headers()
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/organizer/api/review/fixture/media/original-pdf", headers=headers()
            ).status_code
            == 200
        )


def test_original_workbench_uses_trusted_ui_and_main_authenticated_save(tmp_path: Path) -> None:
    app, _, database, root, _ = review_app(tmp_path)
    (root / "index.html").write_text("<script>untrusted-uploaded-script</script>")
    with TestClient(app) as client:
        prefix = "/organizer/api/review/fixture/workbench"
        assert client.get(prefix + "/").status_code == 401
        response = client.get(prefix + "/", headers=headers())
        assert response.status_code == 200, response.text
        assert "图文配对复核" in response.text
        assert "保存到 SQLite 数据库" in response.text
        assert "untrusted-uploaded-script" not in response.text
        assert "fetch('/api/data')" not in response.text
        assert prefix + "/data" in response.text
        response = client.get(prefix + "/data", headers=headers())
        assert response.status_code == 200
        assert len(response.json()["objects"]) == 1
        assert "original_path" not in response.json()["photos"][0]
        response = client.post(
            prefix + "/save-review",
            headers=headers(),
            json={
                "object_id": 1,
                "version": 0,
                "image": "uncertain",
                "text": "context_only",
                "note": "Native UI save",
                "reviewer": "display name",
            },
        )
        assert response.status_code == 200, response.text
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT reviewer,note FROM review_events").fetchone() == (
                "owner",
                "Native UI save",
            )
        assert (
            client.get(prefix + "/media/not-registered.jpg", headers=headers()).status_code == 404
        )


def test_review_resource_snapshot_isolated_in_both_directions(tmp_path: Path) -> None:
    from pastport.adapters.organizer_archives import LocalResourceSnapshot

    source = tmp_path / "source.bin"
    target = tmp_path / "snapshot.bin"
    content = b"x" * (2 * 1024**2)
    source.write_bytes(content)
    LocalResourceSnapshot.copy(source, target)
    assert source.stat().st_ino != target.stat().st_ino
    with source.open("r+b") as original:
        original.write(b"A")
    assert target.read_bytes() == content
    with target.open("r+b") as snapshot:
        snapshot.write(b"B")
    assert source.read_bytes() == b"A" + content[1:]
    assert target.read_bytes() == b"B" + content[1:]


def test_review_resource_snapshot_portable_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pastport.adapters.organizer_archives as archives

    monkeypatch.setattr(sys, "platform", "linux")
    source = tmp_path / "source.bin"
    target = tmp_path / "snapshot.bin"
    source.write_bytes(b"registered resource")
    archives.LocalResourceSnapshot.copy(source, target)
    source.write_bytes(b"changed")
    assert target.read_bytes() == b"registered resource"
