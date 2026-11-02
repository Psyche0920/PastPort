"""HTTP contracts, mode isolation, source ownership and durable job recovery."""

import asyncio
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pastport.adapters.organizer_store import OrganizerStore
from pastport.api.app import create_app
from pastport.api.settings import AppSettings, Credential
from pastport.application.models import Actor, ServiceError
from pastport.application.organizer import OrganizerService
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import (
    OrganizerCatalog, OrganizerJob, OrganizerMaterials, OrganizerSource, OrganizerStart,
)
from test_story_automation import material_fixture

TOKEN = "organizer-test-only-not-a-production-token"


class Production:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.fail = False

    def validate(self, request: GameMakingRequest) -> None:
        assert request.original_pdf.is_file()

    async def run(self, request: GameMakingRequest, start: OrganizerStart,
                  output: Path, *, resume: bool = False) -> None:
        self.calls.append((start.mode, resume))
        if self.fail:
            raise ServiceError("TEST_STOP", "Synthetic execution stopped")
        directory = output / "game-3d"
        directory.mkdir(exist_ok=True)
        (directory / "index.html").write_text("Synthetic host, not visual acceptance")


def setup(root: Path) -> tuple[AppSettings, Production]:
    material_fixture(root / "material")
    directory = root / "material"
    for name in ("saved", "skills", "museum"):
        (directory / name).mkdir()
    for name in ("narrative-draft.json", "input-lock.json", "story-check.json", "budget.json"):
        (directory / "saved" / name).write_text("{}")
    request = GameMakingRequest(
        original_pdf=directory / "original.pdf", source_document=directory / "document.json",
        environment=directory / "environment.json", media_directory=directory / "media",
        saved_story_run=directory / "saved", skills_directory=directory / "skills",
        museum_directory=directory / "museum", output_directory=root / "unused",
        brief="Synthetic private test",
    )
    manifest = root / "request.json"
    manifest.write_text(request.model_dump_json())
    catalog = root / "catalog.json"
    catalog.write_text(OrganizerCatalog(sources=(OrganizerSource(
        source_id="fixture", title="Synthetic contract data", project_id="fixture-project",
        request_file=manifest,
    ),)).model_dump_json())
    settings = AppSettings(
        data_directory=root / "server", organizer_catalog=catalog,
        evidence_mode="disabled", narrative_mode="disabled", resources_mode="disabled",
        accounts=(Credential(token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(), actor=Actor(
            actor_id="owner", roles=("editor",), project_ids=("fixture-project",),
        )), Credential(token_sha256=hashlib.sha256(b"outsider").hexdigest(), actor=Actor(
            actor_id="outsider", roles=("editor",), project_ids=("elsewhere",),
        ))),
    )
    return settings, Production()


def headers(key: str = "run-1") -> dict[str, str]:
    return {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": key}


def await_job(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(150):
        result: dict[str, object] = client.get("/organizer/api/jobs/" + job_id, headers=headers()).json()
        assert "status" in result, result
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(0.02)
    pytest.fail("Job did not settle")


def test_reuse_is_real_idempotent_and_private(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    with TestClient(create_app(settings, organizer_production=production)) as client:
        assert client.get("/organizer/api/sources").status_code == 401
        assert client.get("/organizer/").status_code == 200
        assert client.get("/organizer/assets/app.mjs").status_code == 200
        sources = client.get("/organizer/api/sources", headers=headers()).json()
        assert sources[0]["ready"] is True
        assert "request_file" not in sources[0]
        payload = {"source_id": "fixture", "mode": "reuse"}
        first = client.post("/organizer/api/jobs", json=payload, headers=headers())
        assert first.status_code == 202, first.text
        job_id = first.json()["job_id"]
        assert await_job(client, job_id)["new_model_calls"] == 0
        second = client.post("/organizer/api/jobs", json=payload, headers=headers())
        assert second.json()["job_id"] == job_id
        assert production.calls == [("reuse", False)]
        assert client.get(f"/organizer/api/jobs/{job_id}/preview/index.html", headers=headers()).status_code == 200
        assert client.get(f"/organizer/api/jobs/{job_id}", headers={"Authorization": "Bearer outsider"}).status_code == 403
        assert client.post("/organizer/api/jobs", json={**payload, "mode": "regenerate", "authorize_model": True}, headers=headers()).status_code == 409


def test_regeneration_requires_consent_and_is_not_replay(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    with TestClient(create_app(settings, organizer_production=production)) as client:
        payload = {"source_id": "fixture", "mode": "regenerate"}
        assert client.post("/organizer/api/jobs", json=payload, headers=headers()).status_code == 422
        assert not production.calls
        response = client.post("/organizer/api/jobs", json={**payload, "authorize_model": True}, headers=headers())
        assert response.status_code == 202, response.text
        assert await_job(client, response.json()["job_id"])["status"] == "completed"
        assert production.calls == [("regenerate", False)]


def test_upload_persists_and_rejects_wrong_branch_and_origin(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    with TestClient(create_app(settings, organizer_production=production)) as client:
        assert client.post("/organizer/api/session", headers=headers()).status_code == 200
        edit = {"X-PastPort-Edit": "1"}
        base = "/organizer/api/materials"
        payload = {"project_id": "fixture-project", "entry_level": "mapping"}
        assert client.post(base, json=payload).status_code == 403
        assert client.post(base, json=payload, headers={**edit, "Origin": "https://untrusted.example"}).status_code == 403
        assert client.post(base, json=payload, headers=edit).status_code == 201
        url = base + "/fixture-project/files"
        assert client.post(url+"?role=original_pdf&filename=original.pdf", content=b"not pdf", headers=edit).status_code == 422
        assert client.post(url+"?role=photos&filename=photo.png", content=b"image", headers=edit).status_code == 422
        response = client.post(url+"?role=original_pdf&filename=original.pdf", content=b"%PDF-test", headers=edit)
        assert response.status_code == 201, response.text
        assert response.json()["sha256"] == hashlib.sha256(b"%PDF-test").hexdigest()
        report = client.get(base+"/fixture-project").json()
        assert report["plan"]["stages"][0] == "environment.environment_build"
        assert report["plan"]["missing_roles"] == ["mapping_pdf", "tour"]
        assert not report["plan"]["generation_connected"]
        assert not production.calls
    with TestClient(create_app(settings, organizer_production=production)) as client:
        assert len(client.get(base+"/fixture-project", headers=headers()).json()["materials"]["files"]) == 1


@pytest.mark.parametrize("level,first,required", [
    ("raw", "evidence.photo_mapping", ("original_pdf", "photos")),
    ("mapping", "environment.environment_build", ("original_pdf", "mapping_pdf", "tour")),
    ("vr", "environment.scene3d", ("original_pdf", "matched_vr")),
    ("3d", "story", ("original_pdf", "mounted_3d")),
])
def test_four_start_levels_have_distinct_native_plans(level: str, first: str, required: tuple[str, ...]) -> None:
    material = OrganizerMaterials.model_validate_json(json.dumps({
        "project_id": "p", "owner_id": "o", "entry_level": level,
    }))
    plan = OrganizerService.plan(material)
    assert plan.stages[0] == first
    assert plan.missing_roles == required


def test_only_explicit_recovery_resumes_cached_job(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    production.fail = True
    with TestClient(create_app(settings, organizer_production=production)) as client:
        response = client.post("/organizer/api/jobs", json={"source_id": "fixture", "mode": "reuse"}, headers=headers())
        job_id = response.json()["job_id"]
        assert await_job(client, job_id)["status"] == "failed"
        assert len(production.calls) == 1
        assert client.post(f"/organizer/api/jobs/{job_id}/continue", json={"confirm_continue": False}, headers=headers()).status_code == 422
        production.fail = False
        assert client.post(f"/organizer/api/jobs/{job_id}/continue", json={"confirm_continue": True}, headers=headers()).status_code == 202
        assert await_job(client, job_id)["status"] == "completed"
        assert production.calls == [("reuse", False), ("reuse", True)]


def test_cache_tampering_and_project_misregistration_are_rejected(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    assert settings.organizer_catalog is not None
    catalog = OrganizerCatalog.model_validate_json(settings.organizer_catalog.read_bytes())
    source = catalog.sources[0]
    wrong = source.model_copy(update={"project_id": "another-project"})
    with pytest.raises(ServiceError, match="来源不一致"):
        OrganizerService.request(wrong)
    request = OrganizerService.request(source)
    before = OrganizerService.fingerprint(request)
    (request.saved_story_run / "narrative-draft.json").write_text('{"changed":true}')
    assert OrganizerService.fingerprint(request) != before


def test_environment_preparation_never_runs_story_or_assembly(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    with TestClient(create_app(settings, organizer_production=production)) as client:
        response = client.post("/organizer/api/jobs", headers=headers(), json={
            "source_id": "fixture", "mode": "reuse", "stop_after": "environment",
        })
        assert response.status_code == 202, response.text
        job = await_job(client, response.json()["job_id"])
        assert job["status"] == "environment_ready"
        assert job["prepared_source_id"] == "fixture"
        assert job["result_ready"] is False
        assert job["new_model_calls"] == 0
        assert not production.calls
        assert client.get(f"/organizer/api/jobs/{job['job_id']}/open", headers=headers()).status_code == 409


@pytest.mark.parametrize("mode", ["reuse", "regenerate"])
def test_story_stop_revalidates_without_gameplay_or_assembly(tmp_path: Path, monkeypatch, mode: str) -> None:
    from pastport.adapters.organizer_production import SDKOrganizerProduction
    from pastport.adapters.game_making import SDKGameMakingStages
    from pastport.application.game_making import GameMakingWorkflow

    setup(tmp_path)
    request = GameMakingRequest.model_validate_json((tmp_path / "request.json").read_bytes())
    output = tmp_path / "stage-output"
    output.mkdir()
    calls: list[str] = []

    async def author(self, request, output, **kwargs):
        calls.append("generate")
        return output / "narrative-draft.json"

    async def story(self, request):
        calls.append("validate_saved_story")
        return request.saved_story_run / "narrative-draft.json"

    async def forbidden(self, request):
        pytest.fail("Story preparation reached gameplay or assembly")

    monkeypatch.setattr(SDKOrganizerProduction, "validate", lambda self, request: None)
    monkeypatch.setattr(SDKGameMakingStages, "author_story", author)
    monkeypatch.setattr(SDKGameMakingStages, "story", story)
    monkeypatch.setattr(GameMakingWorkflow, "run", forbidden)
    asyncio.run(SDKOrganizerProduction().run(request, OrganizerStart.model_validate({
        "source_id": "fixture", "mode": mode, "authorize_model": mode == "regenerate",
        "stop_after": "story",
    }), output))
    assert calls == (["generate"] if mode == "regenerate" else []) + ["validate_saved_story"]
    assert (output / "organizer-production-request.json").is_file()
    assert not list(output.rglob("game-3d/index.html"))


def test_story_ready_source_handoff_is_required_and_private(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)

    class StoryProduction(Production):
        async def run(self, request, start, output, *, resume=False):
            self.calls.append((start.mode, resume))
            if start.stop_after == "story":
                (output / "organizer-production-request.json").write_text(request.model_copy(update={"output_directory": output}).model_dump_json())
                return
            await super().run(request, start, output, resume=resume)

    production = StoryProduction()
    with TestClient(create_app(settings, organizer_production=production)) as client:
        response = client.post("/organizer/api/jobs", headers=headers("prepare-story"), json={
            "source_id": "fixture", "mode": "reuse", "stop_after": "story",
        })
        job = await_job(client, response.json()["job_id"])
        assert job["status"] == "story_ready"
        assert job["result_ready"] is False
        assert len(production.calls) == 1
        source = job["prepared_source_id"]
        assert source
        assert client.get("/organizer/api/sources", headers={"Authorization": "Bearer outsider"}).json() == []
        response = client.post("/organizer/api/jobs", headers=headers("make-game"), json={
            "source_id": source, "mode": "reuse", "stop_after": "game",
        })
        assert response.status_code == 202, response.text
        assert await_job(client, response.json()["job_id"])["result_ready"] is True


def test_storage_locations_are_authenticated_and_job_scoped(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    with TestClient(create_app(settings, organizer_production=production)) as client:
        assert client.get("/organizer/api/storage").status_code == 401
        response = client.get("/organizer/api/storage", headers=headers())
        assert response.status_code == 200
        root = (settings.data_directory / "organizer").resolve()
        assert response.json()["cache_directory"] == str(root)
        response = client.post("/organizer/api/jobs", headers=headers(), json={"source_id": "fixture", "mode": "reuse"})
        job = await_job(client, response.json()["job_id"])
        assert job["cache_directory"] == str(root / "jobs" / job["job_id"])
        assert job["game_directory"] == str(root / "jobs" / job["job_id"] / "game-3d")
        assert client.get(f"/organizer/api/jobs/{job['job_id']}", headers={"Authorization": "Bearer outsider"}).status_code == 403


def test_active_source_refresh_does_not_scan_unrelated_history(tmp_path: Path) -> None:
    settings,production=setup(tmp_path)
    catalog=OrganizerCatalog.model_validate_json(settings.organizer_catalog.read_bytes())
    unrelated=OrganizerSource(source_id="unrelated-history",title="Unavailable unrelated history",project_id="fixture-project",request_file=tmp_path/"missing-old-request.json")
    settings.organizer_catalog.write_text(OrganizerCatalog(sources=(*catalog.sources,unrelated)).model_dump_json())
    with TestClient(create_app(settings,organizer_production=production)) as client:
        response=client.get('/organizer/api/sources?active_source_id=fixture',headers=headers())
        assert response.status_code==200,response.text
        assert [s['source_id'] for s in response.json()]==['fixture']
        assert response.json()[0]['ready']
        assert client.get('/organizer/api/sources?active_source_id=unregistered',headers=headers()).status_code==404
        assert client.get('/organizer/api/sources?active_source_id=fixture',headers={'Authorization':'Bearer outsider'}).status_code==403
        assert client.get('/organizer/api/sources?default_only=true',headers=headers()).json()==[]
        catalog=client.get('/organizer/api/sources?metadata_only=true',headers=headers()).json()
        assert {v['source_id'] for v in catalog}=={'fixture','unrelated-history'}
        assert all(not v['ready'] for v in catalog)


def test_organizer_assets_are_versioned_and_not_cached(tmp_path: Path) -> None:
    settings,production=setup(tmp_path)
    with TestClient(create_app(settings,organizer_production=production)) as client:
        page=client.get('/organizer/')
        assert 'assets/app.mjs?v=' in page.text
        script=client.get('/organizer/assets/app.mjs')
        assert "from './review.mjs?v=" in script.text
        assert script.headers['cache-control']=='no-store'
        review=client.get('/organizer/assets/review.mjs')
        assert review.headers['cache-control']=='no-store'
        assert "from './i18n.mjs?v=" in script.text
        assert "from './i18n.mjs?v=" in review.text
        language=client.get('/organizer/assets/i18n.mjs')
        assert language.status_code==200
        assert language.headers['cache-control']=='no-store'
        assert 'interface-language' in page.text
        assert 'mountLocalization' in language.text
        assert '正在自动同步保存的审核版本' not in review.text


@pytest.mark.parametrize("stage,expected", [
    ("evidence", "映射PDF已导出，正在匹配环境物件"),
    ("matched_environment", "挂载3D编号与导航"),
    ("scene3d_1", "校验3D挂载与环境资料"),
])
def test_native_receipts_override_stale_pdf_progress(tmp_path: Path, stage: str, expected: str) -> None:
    store = OrganizerStore(tmp_path / "organizer")
    service = OrganizerService(store, OrganizerCatalog(), Production())
    job = OrganizerJob(job_id="progress-test", owner_id="owner", project_id="fixture-project",
        source_id="uploaded-test", mode="regenerate", status="running", input_kind="uploads",
        entry_level="raw3d", message="Starting", input_sha256="a"*64,
        request_key="progress-request", payload_sha256="b"*64)
    store.save("job",job.job_id,job)
    native = service.directory(job.job_id)/"native"
    (native/"evidence").mkdir(parents=True)
    (native/"evidence/progress.json").write_text(json.dumps({"phase":"export_mapping"}))
    (native/"native-receipts").mkdir()
    (native/"native-receipts"/(stage+".json")).write_text("{}")
    actor=Actor(actor_id="owner",roles=("editor",),project_ids=("fixture-project",))
    assert service.job(job.job_id,actor).message==expected


def test_nested_native_handoff_keeps_its_review_binding(tmp_path: Path) -> None:
    setup(tmp_path)
    service=OrganizerService(OrganizerStore(tmp_path/'organizer'),OrganizerCatalog(),Production())
    job=OrganizerJob(job_id='nested-handoff',owner_id='owner',project_id='fixture-project',
        source_id='uploaded-test',mode='regenerate',status='environment_ready',
        message='Ready',input_sha256='a'*64,request_key='request',payload_sha256='b'*64,
        error_code='OLD_FAILURE')
    root=service.directory(job.job_id)/'native';handoff=root/'handoff';handoff.mkdir(parents=True)
    binding=handoff/'review-binding.json';binding.write_text('{}')
    request=GameMakingRequest.model_validate_json((tmp_path/'request.json').read_bytes()).model_copy(update={'environment':handoff/'environment.json'})
    request_file=root/'prepared-request.json';request_file.write_text(request.model_dump_json())
    source_id=service.register_prepared_source(job,request_file,'Ready',unique=True)
    actor=Actor(actor_id='owner',roles=('editor',),project_ids=('fixture-project',))
    source=service.source(source_id,actor)
    assert source.review_binding_file==binding
    # Previously registered sources can recover the same nested binding too.
    source=source.model_copy(update={'review_binding_file':None})
    assert service.bound_review_source(source,actor).review_binding_file==binding
    service.store.save('job',job.job_id,job)
    assert service.job(job.job_id,actor).error_code is None


def test_workspace_selection_survives_new_session_and_service_restart(tmp_path: Path) -> None:
    settings, production = setup(tmp_path)
    body={"source_id":"fixture"}
    with TestClient(create_app(settings,organizer_production=production)) as client:
        assert client.get('/organizer/api/workspace').status_code==401
        assert client.get('/organizer/api/workspace',headers=headers()).json() is None
        selected=client.post('/organizer/api/workspace',headers=headers(),json=body)
        assert selected.status_code==200,selected.text
        assert selected.json()['project_id']=='fixture-project'
        assert selected.json()['story_ready'] is True
        assert production.calls==[]
        assert client.post('/organizer/api/workspace',headers={'Authorization':'Bearer outsider'},json=body).status_code in (403,404)
        assert client.post('/organizer/api/workspace',headers=headers(),json={'source_id':'missing'}).status_code==404
    with TestClient(create_app(settings,organizer_production=production)) as client:
        assert client.post('/organizer/api/session',headers=headers()).status_code==200
        assert client.get('/organizer/api/workspace').json()==selected.json()
        assert client.delete('/organizer/api/session',headers={'X-PastPort-Edit':'1'}).status_code==204
        assert client.get('/organizer/api/workspace').status_code==401
        assert client.post('/organizer/api/session',headers=headers()).status_code==200
        assert client.get('/organizer/api/workspace').json()==selected.json()
        assert production.calls==[]
