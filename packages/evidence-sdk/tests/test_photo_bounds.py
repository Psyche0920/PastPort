"""Compact deadlines preserve unknown usage and block redispatch."""
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.domain.execution import (
    ExecutionInput, ExecutionOutput, ExecutionRecoveryRequired, ModelExecutionError, SubscriptionGrant,
)
from pastport_evidence.domain.photos import CompactPhotoInspectionPayload


class TimeoutTransport:
    def __init__(self) -> None:
        self.timeouts: list[int] = []

    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        self.timeouts.append(timeout_seconds)
        raise ModelExecutionError("synthetic private context", failure_code="transport_timeout") from TimeoutError()


def test_compact_schema_rejects_excess_counts_and_verbose_text() -> None:
    entity = {"proposal_id": "chair", "label": "chair", "category": "seat", "distinguishing_features": ["red fabric"]}
    for payload in ({"entities": [entity] * 13}, {"entities": [{**entity, "label": "x" * 61}]}, {"gaps": ["x" * 161]}):
        with pytest.raises(ValidationError):
            CompactPhotoInspectionPayload.model_validate_json(json.dumps(payload))
    assert CompactPhotoInspectionPayload.model_json_schema()["properties"]["sightings"]["maxItems"] == 24
    assert CompactPhotoInspectionPayload.model_validate_json('{"gaps":["inventory_incomplete:photo-1"]}').gaps


@pytest.mark.parametrize("version,seconds,expected", [("v2", 240, 120), ("v2", 60, 60), ("v1", 240, 240)])
def test_deadline_and_failure_code_do_not_allow_redispatch(tmp_path: Path, version: str, seconds: int, expected: int) -> None:
    grant = SubscriptionGrant(grant_ref="test-grant", project_id="test-project", timeout_seconds=seconds)
    transport = TimeoutTransport()
    path = tmp_path / "executions.sqlite3"
    executor = SubscriptionExecutor(path, grant, transport)
    request = ExecutionInput(project_id=grant.project_id, grant_ref=grant.grant_ref, model_id=grant.model_id,
        kind="photo_inspection", prompt_version=version, policy_version="photo-identity-v1",
        instructions="Synthetic request", payload_json="{}", output_schema_json="{}")
    with pytest.raises(ModelExecutionError):
        executor.execute(request)
    assert transport.timeouts == [expected]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT error_type,failure_code,cause_type FROM execution_failures").fetchone() == ("ModelExecutionError", "transport_timeout", "TimeoutError")
        assert db.execute("SELECT state,result FROM executions").fetchone() == ("recovery_required", None)
    with pytest.raises(ExecutionRecoveryRequired):
        executor.execute(request)
    assert transport.timeouts == [expected]
    assert b"synthetic private context" not in path.read_bytes()


def test_twenty_unique_objects_stop_discovery_and_preserve_observations(tmp_path: Path) -> None:
    from PIL import Image
    from pastport_evidence.adapters.assets import LocalAssetStore
    from pastport_evidence.adapters.identity import SQLiteSceneRepository
    from pastport_evidence.application.photos import PhotoRegistrar, PhotoRecognitionService
    from pastport_evidence.domain.photos import PhotoInspection, PhotoInspectionRequest

    class Inspector:
        calls = 0
        def inspect_photos(self, request: PhotoInspectionRequest) -> PhotoInspection:
            self.calls += 1
            items = [{"proposal_id": f"p{self.calls}-{i}", "label": f"object {self.calls}-{i}",
                "category": "fixture", "distinguishing_features": [f"feature {i}"]} for i in range(12)]
            return PhotoInspection.model_validate_json(json.dumps({"entities": items,
                "sightings": [{"target_ref": x["proposal_id"], "photo_id": request.photos[0].photo_id,
                    "region": {"top_left": {"x": 0, "y": 0}, "bottom_right": {"x": 4, "y": 4}},
                    "basis": "Visible fixture"} for x in items],
                "gaps": ["inventory_incomplete:background"], "receipt_ref": f"receipt:{self.calls}"}))
    paths = []
    for i in range(6):
        p = tmp_path / f"photo-{i}.png"
        Image.new("RGB", (16, 16), (i * 30, 0, 0)).save(p)
        paths.append(p)
    assets = LocalAssetStore(tmp_path / "assets")
    photos = PhotoRegistrar(assets).register("fixture", tuple(paths))
    artifacts = tmp_path / "runs/one"
    artifacts.mkdir(parents=True)
    inspector = Inspector()
    service = PhotoRecognitionService(SQLiteSceneRepository(tmp_path / "identities.sqlite3"),
        inspector, assets, batch_size=2, entity_limit=20)
    inventory = service.run("fixture", photos, artifacts, "grant", "model", 100)
    assert len(inventory.entities) == 20
    assert len(inventory.observations) == 20
    assert inspector.calls == 2
    assert len({e.object_id for e in inventory.entities}) == 20
    assert service.run("fixture", photos, artifacts, "grant", "model", 100) == inventory
    assert inspector.calls == 2


def test_manual_retry_preserves_unknown_slot_and_counts_it_against_limit(tmp_path: Path) -> None:
    from pastport_evidence.domain.execution import ExecutionDenied
    grant = SubscriptionGrant(grant_ref="g", project_id="p", max_calls=1)
    transport = TimeoutTransport()
    path = tmp_path / "ledger.sqlite3"
    executor = SubscriptionExecutor(path, grant, transport)
    request = ExecutionInput(project_id="p", grant_ref="g", model_id=grant.model_id,
        kind="photo_inspection", prompt_version="v3", policy_version="test",
        instructions="test", payload_json="{}", output_schema_json="{}")
    with pytest.raises(ModelExecutionError):executor.execute(request)
    with sqlite3.connect(path) as db:
        original = db.execute("SELECT * FROM executions").fetchall()
        binding = original[0][2]
    executor.approve_interrupted_retry(binding, "User approved replacing interrupted call")
    assert executor.remaining_calls() == 0
    with pytest.raises(ExecutionDenied):executor.execute(request)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM executions").fetchall() == original
        assert db.execute("SELECT count(*) FROM execution_recoveries").fetchone()[0] == 1
    assert len(transport.timeouts) == 1


def test_approved_replacement_reuses_completed_result_and_keeps_failed_attempt(tmp_path: Path) -> None:
    class Transport:
        calls = 0
        def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
            self.calls += 1
            if self.calls == 2:
                raise ModelExecutionError("interrupted")
            return ExecutionOutput(payload_json="{}", receipt_ref="test", thread_ref="test", turn_ref="test", input_tokens=1, output_tokens=1, total_tokens=2)
    grant = SubscriptionGrant(grant_ref="g", project_id="p", max_calls=5)
    transport = Transport()
    path = tmp_path / "ledger.sqlite3"
    executor = SubscriptionExecutor(path, grant, transport)
    first = ExecutionInput(project_id="p", grant_ref="g", model_id=grant.model_id, kind="pdf_matching", prompt_version="v2", policy_version="test", instructions="test", payload_json="{}", output_schema_json="{}")
    second = first.model_copy(update={"payload_json": '{"page":2}'})
    saved = executor.execute(first)
    with pytest.raises(ModelExecutionError):executor.execute(second)
    with sqlite3.connect(path) as db:
        binding = db.execute("SELECT binding FROM executions WHERE state='recovery_required'").fetchone()[0]
    executor.approve_interrupted_retry(binding, "Explicit operator recovery")
    assert executor.execute(first) == saved
    assert transport.calls == 2
    executor.execute(second)
    assert transport.calls == 3
    executor.execute(second)
    assert transport.calls == 3
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT state,result FROM executions WHERE binding=?", (binding,)).fetchone() == ("recovery_required", None)
        assert db.execute("SELECT count(*) FROM executions").fetchone()[0] == 3
    assert executor.remaining_calls() == 2


def test_token_amendment_keeps_original_grant_and_call_limit(tmp_path: Path) -> None:
    grant = SubscriptionGrant(project_id="p", grant_ref="g", max_calls=2, max_recorded_tokens=1)
    executor = SubscriptionExecutor(tmp_path / "ledger.sqlite3", grant, TimeoutTransport())
    executor.authorize_token_limit(1_000_000, "User explicitly raised task token threshold")
    assert executor.remaining_calls() == 2
    with sqlite3.connect(tmp_path / "ledger.sqlite3") as db:
        assert json.loads(db.execute("SELECT payload FROM execution_grants").fetchone()[0])["max_recorded_tokens"] == 1
        assert db.execute("SELECT token_limit FROM execution_budget_amendments").fetchone()[0] == 1_000_000
    with pytest.raises(ValueError):executor.authorize_token_limit(2_000_000, "too high")


@pytest.mark.parametrize("indices,valid", [([2, 5], True), ([99], False), ([2, 2], False)])
def test_candidate_page_plan_is_text_only_and_rejects_wrong_source_pages(tmp_path: Path, indices: list[int], valid: bool) -> None:
    from pastport_evidence.adapters.assets import LocalAssetStore
    from pastport_evidence.adapters.codex_semantics import CodexSemanticGateway
    from pastport_evidence.domain.build import CandidatePageRequest, CandidateTextPage
    class Executor:
        grant = SubscriptionGrant(project_id="p", grant_ref="g")
        calls = 0
        def execute(self, request: ExecutionInput) -> ExecutionOutput:
            self.calls += 1
            assert request.image_paths == ()
            assert request.prompt_version == "index-v1"
            return ExecutionOutput(payload_json=json.dumps({"page_indices":indices,"gaps":[]}),receipt_ref="test",thread_ref="test",turn_ref="test",input_tokens=1,output_tokens=1,total_tokens=2)
    executor = Executor()
    gateway = CodexSemanticGateway(executor, LocalAssetStore(tmp_path / "assets"))
    request = CandidatePageRequest(objects=(),source_sha256="a"*64,pages=(CandidateTextPage(page_index=2,text="architecture"),CandidateTextPage(page_index=5,text="school")))
    if valid:
        assert gateway.candidate_pages(request, executor.grant).page_indices == (2, 5)
    else:
        with pytest.raises(ValueError):gateway.candidate_pages(request, executor.grant)
    assert executor.calls == 1


def test_authorized_token_removal_keeps_usage_and_finite_call_ceiling(tmp_path: Path) -> None:
    from pastport_evidence.domain.execution import ExecutionDenied
    class Transport:
        calls = 0
        def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
            self.calls += 1
            return ExecutionOutput(payload_json="{}",receipt_ref="r",thread_ref="t",turn_ref="u",input_tokens=10,output_tokens=10,total_tokens=20)
    grant = SubscriptionGrant(project_id="p",grant_ref="g",max_calls=2,max_recorded_tokens=1)
    transport = Transport()
    path = tmp_path / "ledger.sqlite3"
    executor = SubscriptionExecutor(path,grant,transport)
    first = ExecutionInput(project_id="p",grant_ref="g",model_id=grant.model_id,kind="pdf_matching",prompt_version="v2",policy_version="test",instructions="test",payload_json="{}",output_schema_json="{}")
    saved=executor.execute(first)
    assert executor.remaining_calls()==0
    executor.remove_token_threshold("User explicitly removed token threshold")
    assert executor.remaining_calls()==1
    assert executor.execute(first)==saved and transport.calls==1
    executor.execute(first.model_copy(update={"payload_json":'{"page":2}'}))
    assert executor.remaining_calls()==0
    with pytest.raises(ExecutionDenied):executor.execute(first.model_copy(update={"payload_json":'{"page":3}'}))
    with sqlite3.connect(path) as db:
        assert sum(json.loads(row[0])["total_tokens"] for row in db.execute("select result from executions where state='completed'"))==40
