"""Private continuation preserves uncertainty without giving publication authority."""

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from test_service import create_run, headers, settings, wait_for

from pastport.adapters.content import LocalContentFiles, LocalNarrativeAdapter
from pastport.api.app import create_app
from pastport.application.updates import updated
from pastport.domain.modules import CandidateSetDraft, DiscoverRequest, ModuleResult
from pastport.ports.modules import ExecutionContext


class UnverifiedDirection(LocalNarrativeAdapter):
    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        result = await super().discover(request, context)
        assert result.payload is not None
        return updated(
            result,
            payload=updated(
                result.payload,
                candidates=tuple(
                    updated(candidate, blocking_gaps=("Unverified source attribution",))
                    for candidate in result.payload.candidates
                ),
            ),
        )


def test_operator_authorized_preview_retains_unverified_direction(tmp_path: Path) -> None:
    config = settings(tmp_path)
    credential = config.accounts[0]
    config = replace(
        config,
        accounts=(
            updated(
                credential,
                actor=updated(credential.actor, roles=(*credential.actor.roles, "operator")),
            ),
            *config.accounts[1:],
        ),
    )
    assert config.fixture_directory is not None
    adapter = UnverifiedDirection(LocalContentFiles(config.fixture_directory, allow_synthetic=True))
    with TestClient(create_app(config, narrative=adapter)) as client:
        run_id = create_run(client)
        record = wait_for(client, run_id, "needs_review")
        comparison = next(a for a in record.artifacts if a.reference.kind == "candidate_set")
        candidate = CandidateSetDraft.model_validate_json(comparison.payload_json).candidates[0]
        command = dict(
            expected_revision=record.state.revision,
            candidate_set_hash=comparison.reference.sha256,
            candidate_id=candidate.candidate_id,
            reason="Automated private preview",
        )
        assert (
            client.post(
                f"/api/v1/runs/{run_id}/candidate-selections", headers=headers(), json=command
            ).status_code
            == 409
        )
        response = client.post(
            f"/api/v1/runs/{run_id}/internal-preview-continuation",
            headers=headers(),
            json=dict(
                expected_revision=record.state.revision,
                reason="Owner authorized unverified internal preview",
            ),
        )
        assert response.status_code == 200, response.text
        enabled = response.json()
        assert enabled["control"]["internal_preview_continuation"] is True
        assert "Unverified source attribution" in next(
            a["payload_json"]
            for a in enabled["artifacts"]
            if a["reference"]["kind"] == "candidate_set"
        )
        command["expected_revision"] = enabled["state"]["revision"]
        selected = client.post(
            f"/api/v1/runs/{run_id}/candidate-selections", headers=headers(), json=command
        )
        assert selected.status_code == 202, selected.text
        assert selected.json()["review_decisions"] == []


def test_preview_enable_requires_operator_role(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id = create_run(client)
        record = wait_for(client, run_id, "needs_review")
        response = client.post(
            f"/api/v1/runs/{run_id}/internal-preview-continuation",
            headers=headers(),
            json=dict(expected_revision=record.state.revision, reason="No operator authority"),
        )
        assert response.status_code == 403
        current = client.get(f"/api/v1/runs/{run_id}", headers=headers()).json()
        assert current["control"]["internal_preview_continuation"] is False
