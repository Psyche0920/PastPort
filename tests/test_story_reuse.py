"""Story reuse retains text, checks dependencies and never calls a model for rebinding."""

import asyncio
import json

import pytest
from test_story_automation import ROOT, material_fixture
from test_story_plan import PlanProvider

from pastport.adapters.story_reuse import StoryReuseAdapter
from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.story_inputs import (
    EnvironmentContentRevision,
    EnvironmentSnapshot,
    EnvironmentSpatialRevision,
)
from pastport.domain.story_reuse import StoryReuseReport


@pytest.fixture
def authored(tmp_path):
    materials = material_fixture(tmp_path / "old")
    provider = PlanProvider()
    story = tmp_path / "story"
    asyncio.run(
        StoryAutomationWorkflow(
            materials, story, ROOT / "skills", "Synthetic reuse", provider
        ).run()
    )

    def request(base, saved, output):
        return GameMakingRequest(
            original_pdf=base / "original.pdf",
            source_document=base / "document.json",
            environment=base / "environment.json",
            media_directory=base / "media",
            museum_directory=base,
            saved_story_run=saved,
            skills_directory=ROOT / "skills",
            brief="Synthetic reuse",
            output_directory=output,
        )

    old = request(tmp_path / "old", story, tmp_path / "unused")
    material_fixture(tmp_path / "new")
    out = tmp_path / "reuse"
    out.mkdir()
    saved = out / "saved"
    saved.mkdir()
    current = request(tmp_path / "new", saved, out)
    return old, current, out, provider


def update_environment(path, change):
    from pastport.domain.story_inputs import MetricSpatialContent, SpatialWorld

    document = json.loads(path.read_text())
    change(document)
    content = EnvironmentContentRevision.model_validate_json(
        json.dumps({"objects": document["objects"]})
    )
    document["content_revision"] = CanonicalSerializer.digest(content)
    spatial = EnvironmentSpatialRevision.model_validate_json(
        json.dumps(
            {
                "entry_view_id": document["entry_view_id"],
                "views": document["views"],
                "positions": document["positions"],
            }
        )
    )
    document["spatial_revision"] = CanonicalSerializer.digest(spatial)
    for world in document["metric_spatial"]["worlds"]:
        world["interaction_content_revision"] = document["content_revision"]
        geometry = world["geometry"]
        base = SpatialWorld.model_validate_json(json.dumps({**world, "geometry": None}))
        if geometry is not None:
            geometry["input_sha256"] = CanonicalSerializer.digest(base)
    metric = MetricSpatialContent.model_validate_json(
        json.dumps(
            {
                "worlds": document["metric_spatial"]["worlds"],
                "rules": document["metric_spatial"]["rules"],
            }
        )
    )
    document["metric_spatial"]["revision"] = CanonicalSerializer.digest(metric)
    EnvironmentSnapshot.model_validate_json(json.dumps(document))
    path.write_text(json.dumps(document))


def test_position_edit_reuses_text_and_rebinds_without_model(authored):
    old, current, out, provider = authored
    original = (old.saved_story_run / "narrative-draft.json").read_bytes()
    update_environment(current.environment, lambda d: d["positions"][0].update(yaw=1.0, version=1))
    prepared = StoryReuseAdapter().prepare(old, current, out)
    proof = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert proof.status == "compatible", proof.issues
    assert (prepared.saved_story_run / "narrative-draft.json").read_bytes() == original
    assert (old.saved_story_run / "narrative-draft.json").read_bytes() == original
    assert (
        prepared.saved_story_run / "environment-input.json"
    ).read_bytes() == current.environment.read_bytes()
    StoryReuseAdapter().verify(prepared)
    assert provider.calls == 1
    assert proof.new_model_calls == 0
    current.environment.write_text(current.environment.read_text() + " ")
    with pytest.raises(ServiceError, match="compatibility|兼容"):
        StoryReuseAdapter().verify(prepared)


def test_changed_task_evidence_is_blocked_with_task_identity(authored):
    old, current, out, provider = authored
    update_environment(
        current.environment,
        lambda d: d["objects"][0].update(historical_id="fixture-building/other"),
    )
    StoryReuseAdapter().prepare(old, current, out)
    proof = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert proof.status == "incompatible"
    assert any("task-1" in issue and "史料" in issue for issue in proof.issues)
    assert not (current.saved_story_run / "narrative-draft.json").exists()
    assert provider.calls == 1


def test_changed_task_introduction_requires_review(authored):
    old, current, out, _ = authored
    update_environment(
        current.environment,
        lambda d: d["objects"][0].update(introduction="Contradictory new label"),
    )
    StoryReuseAdapter().prepare(old, current, out)
    proof = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert proof.status == "needs_confirmation"
    assert any("task-1" in issue and "介绍" in issue for issue in proof.issues)


def test_changed_review_verdict_does_not_force_rewrite_when_task_still_valid(authored):
    old, current, out, provider = authored
    update_environment(
        current.environment,
        lambda d: d["objects"][0].update(
            image_review="suitable", text_review="context_only", pairing_version=1
        ),
    )
    prepared = StoryReuseAdapter().prepare(old, current, out)
    proof = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert proof.status == "compatible", proof.issues
    StoryReuseAdapter().verify(prepared)
    assert provider.calls == 1


def test_organizer_automatically_checks_latest_story_in_its_lineage(authored, tmp_path):
    from fastapi.testclient import TestClient
    from test_organizer import Production, await_job, headers, setup

    from pastport.adapters.organizer_store import OrganizerStore
    from pastport.api.app import create_app
    from pastport.domain.organizer import OrganizerJob
    from pastport.domain.organizer_inputs import RegisteredNativeSource

    old, current, _, provider = authored
    root = tmp_path / "api"
    root.mkdir()
    settings, _ = setup(root)
    (root / "request.json").write_text(current.model_dump_json())
    parent = root / "parent-request.json"
    parent.write_text(old.model_dump_json())
    store = OrganizerStore(settings.data_directory / "organizer")
    store.save(
        "native_source",
        "prepared-story",
        RegisteredNativeSource(
            owner_id="owner",
            project_id="fixture-project",
            source_id="prepared-story",
            title="Saved synthetic story",
            request_file=parent,
            parent_source_id="fixture",
        ),
    )
    store.save(
        "job",
        "old-story",
        OrganizerJob(
            job_id="old-story",
            owner_id="owner",
            project_id="fixture-project",
            source_id="fixture",
            mode="regenerate",
            status="story_ready",
            message="Synthetic completed story",
            input_sha256="a" * 64,
            request_key="old-story-key",
            payload_sha256="b" * 64,
            prepared_source_id="prepared-story",
        ),
    )

    class ReuseProduction(Production):
        async def run(self, request, start, output, *, resume=False):
            StoryReuseAdapter().verify(request)
            self.calls.append((start.mode, resume))
            (output / "organizer-production-request.json").write_text(
                request.model_copy(update={"output_directory": output}).model_dump_json()
            )

    production = ReuseProduction()
    with TestClient(
        create_app(
            settings, organizer_production=production, organizer_story_reuse=StoryReuseAdapter()
        )
    ) as client:
        endpoint = "/organizer/api/sources/fixture/story-compatibility"
        assert client.post(endpoint).status_code == 401
        assert (
            client.post(endpoint, headers={"Authorization": "Bearer outsider"}).status_code == 403
        )
        initial = next(
            v
            for v in client.get("/organizer/api/sources", headers=headers()).json()
            if v["source_id"] == "fixture"
        )
        assert not initial["reuse_ready"] and not initial["reuse_checked"]
        response = client.post(endpoint, headers=headers())
        assert response.status_code == 200, response.text
        identifier = response.json()["source_id"]
        value = next(
            v
            for v in client.get("/organizer/api/sources", headers=headers()).json()
            if v["source_id"] == identifier
        )
        assert value["reuse_ready"] and value["reuse_checked"] and not value["reuse_issues"]
        run = client.post(
            "/organizer/api/jobs",
            headers=headers("reuse-compatible-story"),
            json={"source_id": identifier, "mode": "reuse", "stop_after": "story"},
        )
        assert run.status_code == 202, run.text
        job = await_job(client, run.json()["job_id"])
        assert job["status"] == "story_ready", job
        assert job["new_model_calls"] == 0
        assert production.calls == [("reuse", False)]
        assert provider.calls == 1


def test_unused_object_edits_do_not_block_existing_tasks(authored):
    old, current, out, provider = authored
    import shutil

    shutil.copyfile(
        current.media_directory / "history-01.png", current.media_directory / "history-02.png"
    )

    def add_unused(document):
        obj = dict(document["objects"][0])
        obj.update(
            object_number=2,
            stable_id="unused-two",
            name="Another hatch",
            introduction="Different unused label",
        )
        document["objects"].append(obj)

    update_environment(current.environment, add_unused)
    prepared = StoryReuseAdapter().prepare(old, current, out)
    proof = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert proof.status == "compatible", proof.issues
    StoryReuseAdapter().verify(prepared)
    assert provider.calls == 1


def test_introduction_confirmation_is_bound_and_does_not_bypass_critical_changes(authored):
    from datetime import UTC, datetime

    from pastport.domain.story_reuse import StoryReuseDecision

    old, current, out, provider = authored
    update_environment(
        current.environment, lambda d: d["objects"][0].update(introduction="Reviewed wording")
    )
    StoryReuseAdapter().prepare(old, current, out)
    pending = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert pending.status == "needs_confirmation"
    decision = StoryReuseDecision(
        actor_id="owner",
        decided_at=datetime.now(UTC),
        report_sha256=CanonicalSerializer.digest(pending),
        environment_sha256=pending.environment_sha256,
        parent_draft_sha256=pending.parent_draft_sha256,
        introduction_changes=pending.introduction_changes,
    )
    prepared = StoryReuseAdapter().prepare(old, current, out, decision=decision)
    ready = StoryReuseReport.model_validate_json((out / "story-compatibility.json").read_bytes())
    assert ready.status == "compatible" and ready.confirmation.actor_id == "owner"
    assert ready.confirmation.report_sha256 == CanonicalSerializer.digest(pending)
    assert (prepared.saved_story_run / "narrative-draft.json").read_bytes() == (
        old.saved_story_run / "narrative-draft.json"
    ).read_bytes()
    StoryReuseAdapter().verify(prepared)
    assert provider.calls == 1
    blocked_out = out.parent / "blocked"
    blocked_out.mkdir()
    saved = blocked_out / "saved"
    saved.mkdir()
    update_environment(
        current.environment,
        lambda d: d["objects"][0].update(historical_id="fixture-building/changed"),
    )
    StoryReuseAdapter().prepare(
        old, current.model_copy(update={"saved_story_run": saved}), blocked_out, decision=decision
    )
    blocked = StoryReuseReport.model_validate_json(
        (blocked_out / "story-compatibility.json").read_bytes()
    )
    assert blocked.status == "incompatible" and not blocked.introduction_changes
    assert not (saved / "narrative-draft.json").exists()


def test_http_confirmation_requires_current_report_and_authorized_actor(authored, tmp_path):
    from fastapi.testclient import TestClient
    from test_organizer import headers, setup

    from pastport.adapters.organizer_store import OrganizerStore
    from pastport.api.app import create_app
    from pastport.domain.organizer import OrganizerJob
    from pastport.domain.organizer_inputs import RegisteredNativeSource

    old, current, _, provider = authored
    update_environment(
        current.environment, lambda d: d["objects"][0].update(introduction="Reviewed wording")
    )
    root = tmp_path / "confirmation-api"
    root.mkdir()
    settings, production = setup(root)
    (root / "request.json").write_text(current.model_dump_json())
    pointer = root / "parent.json"
    pointer.write_text(old.model_dump_json())
    store = OrganizerStore(settings.data_directory / "organizer")
    store.save(
        "native_source",
        "baseline",
        RegisteredNativeSource(
            owner_id="owner",
            project_id="fixture-project",
            source_id="baseline",
            title="Baseline",
            request_file=pointer,
            parent_source_id="fixture",
        ),
    )
    store.save(
        "job",
        "baseline-job",
        OrganizerJob(
            job_id="baseline-job",
            owner_id="owner",
            project_id="fixture-project",
            source_id="fixture",
            mode="regenerate",
            status="story_ready",
            message="Baseline",
            input_sha256="a" * 64,
            request_key="baseline-key",
            payload_sha256="b" * 64,
            prepared_source_id="baseline",
        ),
    )
    with TestClient(
        create_app(
            settings, organizer_production=production, organizer_story_reuse=StoryReuseAdapter()
        )
    ) as client:
        checked = client.post(
            "/organizer/api/sources/fixture/story-compatibility", headers=headers()
        ).json()["source_id"]
        view = client.get(
            "/organizer/api/sources?active_source_id=" + checked, headers=headers()
        ).json()[0]
        assert (
            not view["reuse_ready"] and view["reuse_confirmation_sha256"] and view["reuse_changes"]
        )
        endpoint = "/organizer/api/sources/" + checked + "/confirm-story-reuse"
        body = {"report_sha256": view["reuse_confirmation_sha256"], "confirm_unchanged_story": True}
        assert client.post(endpoint, json=body).status_code == 401
        assert (
            client.post(
                endpoint, headers={"Authorization": "Bearer outsider"}, json=body
            ).status_code
            == 404
        )
        assert (
            client.post(
                endpoint, headers=headers(), json={**body, "report_sha256": "0" * 64}
            ).status_code
            == 409
        )
        response = client.post(endpoint, headers=headers(), json=body)
        assert response.status_code == 200, response.text
        confirmed = response.json()["source_id"]
        result = client.get(
            "/organizer/api/sources?active_source_id=" + confirmed, headers=headers()
        ).json()[0]
        assert result["reuse_ready"] and result["reuse_confirmation_sha256"] is None
        assert provider.calls == 1
        update_environment(
            current.environment, lambda d: d["objects"][0].update(introduction="Another edit")
        )
        assert client.post(endpoint, headers=headers(), json=body).status_code == 409
