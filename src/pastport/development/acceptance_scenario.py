"""Authenticated test-only workflow scenario for interchangeable offline ports."""

import hashlib
import secrets
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi.testclient import TestClient

from pastport.api.app import create_app
from pastport.api.settings import AppSettings, Credential
from pastport.application.models import (
    Actor,
    CreateProject,
    CreateRun,
    ProjectRecord,
    ReviewChoice,
    RunRecord,
    SelectCandidate,
    SubmitReview,
)
from pastport.application.previews import CreatePreview, PreviewView, PrivatePackageView
from pastport.development.acceptance_models import AcceptanceCase, AcceptanceCheck, CaseName
from pastport.domain.common import ArtifactRef, Contract
from pastport.domain.modules import CandidateSetDraft, InventoryRequest
from pastport.domain.player_saves import CreatePlayerSave, PlayerSaveView
from pastport.domain.workflow import BudgetPolicy
from pastport.ports.modules import EvidencePort, NarrativePort
from pastport.ports.resources import ResourceReader


class AcceptanceFailure(RuntimeError):
    """Expose an operation/code, never project text or raw provider failures."""


class ModuleModes(Contract):
    evidence: Literal["local", "injected", "disabled"]
    narrative: Literal["local", "injected", "disabled"]
    resources: Literal["local", "injected", "disabled"]


class HealthView(Contract):
    status: Literal["ready", "unavailable"]
    environment: Literal["test", "production"]
    modules: ModuleModes


class WorkflowAcceptance:
    def __init__(self, client: TestClient, token: str, timeout_seconds: float) -> None:
        self.client = client
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.checks: list[AcceptanceCheck] = []

    def request[T: Contract](self, path: str, model: type[T], payload: Contract | None = None) -> T:
        headers = {"Authorization": "Bearer " + self.token, "Idempotency-Key": str(uuid4())}
        response = (
            self.client.get(path, headers=headers)
            if payload is None
            else self.client.post(path, headers=headers, json=payload.model_dump(mode="json"))
        )
        if response.status_code >= 400:
            raise AcceptanceFailure("HTTP_" + str(response.status_code))
        return model.model_validate_json(response.content)

    def check(self, operation: str, passed: bool, detail: str) -> None:
        self.checks.append(AcceptanceCheck(operation=operation, passed=passed, detail=detail))
        if not passed:
            raise AcceptanceFailure(operation)

    def wait(self, run_id: str, status: str) -> RunRecord:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            record = self.request("/api/v1/runs/" + run_id, RunRecord)
            if record.state.status == status:
                return record
            if record.state.status in ("failed", "blocked", "budget_exhausted", "cancelled"):
                error = record.state.last_error
                raise AcceptanceFailure(error.code if error else record.state.status)
            time.sleep(0.02)
        raise AcceptanceFailure("STAGE_TIMEOUT")

    def approve(self, run_id: str, gate: str) -> None:
        record = self.wait(run_id, "waiting_review")
        review = next(
            item
            for item in record.review_requests
            if item.request_id == record.state.pending_review_id
        )
        self.check("review_" + gate, review.gate == gate, "Explicit test-only gate command")
        self.request(
            f"/api/v1/runs/{run_id}/review-decisions",
            RunRecord,
            SubmitReview(
                expected_revision=record.state.revision,
                request_id=review.request_id,
                decisions=tuple(
                    ReviewChoice(
                        target_id=item.target_id,
                        target_version=item.version,
                        target_hash=item.sha256,
                        decision="approved",
                        reason="Automated synthetic acceptance, not professional approval",
                    )
                    for item in review.targets
                ),
            ),
        )

    def run(self, name: CaseName, fixtures: Path, expected: ModuleModes) -> AcceptanceCase:
        health = self.request("/api/v1/health", HealthView)
        self.check(
            "composition",
            health.environment == "test" and health.modules == expected,
            "Actual module selection matches the requested combination",
        )
        inventory = InventoryRequest.model_validate_json(
            (fixtures / "inventory-request.json").read_bytes()
        )
        project_id = inventory.requirements.project_id
        prefix = "/api/v1/projects/" + project_id
        self.request(
            "/api/v1/projects",
            ProjectRecord,
            CreateProject(
                name="Synthetic module acceptance",
                provider=inventory.folder.provider,
                folder_id=inventory.folder.folder_id,
                requirements=inventory.requirements,
            ),
        )
        policy_ref = self.request(prefix + "/policy", ArtifactRef)
        record = self.request(
            prefix + "/runs",
            RunRecord,
            CreateRun(
                policy_ref=policy_ref,
                budget_policy=BudgetPolicy.model_validate_json(
                    (fixtures / "budget-policy.json").read_bytes()
                ),
            ),
        )
        run_id = record.state.run_id
        path = "/api/v1/runs/" + run_id
        record = self.wait(run_id, "needs_review")
        candidates = next(
            item for item in reversed(record.artifacts) if item.reference.kind == "candidate_set"
        )
        payload = CandidateSetDraft.model_validate_json(candidates.payload_json)
        if not payload.candidates:
            raise AcceptanceFailure("NO_CANDIDATES")
        self.request(
            path + "/candidate-selections",
            RunRecord,
            SelectCandidate(
                expected_revision=record.state.revision,
                candidate_set_hash=candidates.reference.sha256,
                candidate_id=payload.candidates[0].candidate_id,
                reason="Explicit synthetic direction selection",
            ),
        )
        self.approve(run_id, "evidence")
        record = self.wait(run_id, "waiting_review")
        draft = next(
            item
            for item in reversed(record.artifacts)
            if item.reference.artifact_id.endswith(":draft")
        )
        preview = self.request(
            path + "/previews",
            PreviewView,
            CreatePreview(expected_revision=record.state.revision, source_ref=draft.reference),
        )
        unchanged = self.request(path, RunRecord)
        self.check(
            "draft_preview",
            preview.kind == "test" and unchanged == record,
            "Draft preview is available before narrative approval without changing the run",
        )
        self.approve(run_id, "narrative")
        self.approve(run_id, "publication")
        final = self.wait(run_id, "published")
        if final.current_release_id is None:
            raise AcceptanceFailure("RELEASE_MISSING")
        package = self.request(
            prefix + "/releases/" + final.current_release_id + "/package", PrivatePackageView
        )
        self.check(
            "release_binding",
            package.runtime_package.project_id == project_id
            and package.runtime_ref
            == next(
                item.reference
                for item in reversed(final.artifacts)
                if item.reference.kind == "runtime"
            ),
            "Current private runtime package revalidates through the real loader",
        )
        for asset in package.runtime_package.media_manifest:
            response = self.client.get(
                prefix + "/releases/" + final.current_release_id + "/assets/" + asset.asset_id,
                headers={"Authorization": "Bearer " + self.token},
            )
            self.check(
                "media_" + asset.asset_id,
                response.status_code == 200,
                "Registered private media resolves with server hash checks",
            )
        saved = self.request(
            prefix + "/player-saves", PlayerSaveView, CreatePlayerSave(save_id="acceptance-save")
        )
        restored = self.request(prefix + "/player-saves/acceptance-save", PlayerSaveView)
        self.check(
            "player_restore",
            saved == restored and saved.state.package_hash == package.runtime_ref.sha256,
            "F7 initializes and restores a durable save bound to this exact package",
        )
        self.check(
            "private_only",
            self.client.get("/api/v1/public/projects/" + project_id + "/release").status_code
            == 404,
            "No public publication endpoint is enabled",
        )
        return AcceptanceCase(
            name=name,
            status="passed",
            checks=tuple(self.checks),
            detail="Synthetic HTTP/SQLite/workflow/package/player scenario passed",
            run_id=run_id,
            release_id=final.current_release_id,
            runtime_ref=package.runtime_ref,
            review_gates=tuple(sorted({item.gate for item in final.review_decisions})),
        )


def scenario(
    name: CaseName,
    fixtures: Path,
    data: Path,
    timeout_seconds: float,
    evidence: EvidencePort | None,
    narrative: NarrativePort | None,
    resources: ResourceReader,
) -> AcceptanceCase:
    token = secrets.token_urlsafe(32)
    both_injected = evidence is not None and narrative is not None
    configuration = AppSettings(
        data_directory=data,
        environment="test",
        fixture_directory=None if both_injected else fixtures,
        accounts=(
            Credential(
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                actor=Actor(
                    actor_id="acceptance-reviewer",
                    project_ids=None,
                    roles=("editor", "evidence", "narrative", "publisher"),
                ),
            ),
        ),
    )
    with TestClient(
        create_app(configuration, evidence=evidence, narrative=narrative, resources=resources)
    ) as client:
        acceptance = WorkflowAcceptance(client, token, timeout_seconds)
        try:
            return acceptance.run(
                name,
                fixtures,
                ModuleModes(
                    evidence="injected" if evidence is not None else "local",
                    narrative="injected" if narrative is not None else "local",
                    resources="injected",
                ),
            )
        except AcceptanceFailure as error:
            return AcceptanceCase(
                name=name, status="failed", checks=tuple(acceptance.checks), detail=str(error)
            )
