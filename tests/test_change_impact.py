"""Actual version-bound diff without granting or rewriting approvals."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from test_previews import narrative_review
from test_service import RESTRICTED_TOKEN, headers, settings

from pastport.api.app import create_app
from pastport.application.change_impact import ChangeImpactService


def test_saved_revision_diff_is_conservative_and_does_not_mutate_run(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        run_id, run = narrative_review(client)
        before = next(
            item
            for item in reversed(run.artifacts)
            if item.reference.artifact_id.endswith(":draft")
        )
        replacement = json.loads(before.payload_json)
        replacement["package"]["game"]["locales"][0]["entries"][0]["text"] += (
            " Updated original wording"
        )
        result = client.post(
            f"/api/v1/runs/{run_id}/revisions",
            headers=headers(),
            json={
                "expected_revision": run.state.revision,
                "reason": "Clarify wording",
                "replacement_story": replacement,
                "facts_changed": False,
            },
        )
        assert result.status_code == 202, result.text
        current = result.json()
        after = next(
            item
            for item in reversed(current["artifacts"])
            if item["reference"]["artifact_id"].endswith(":draft")
        )
        payload = {
            "before_ref": before.reference.model_dump(mode="json"),
            "after_ref": after["reference"],
        }
        path = f"/api/v1/runs/{run_id}/change-impact"
        assert client.post(path, json=payload).status_code == 401
        assert (
            client.post(path, headers=headers(token=RESTRICTED_TOKEN), json=payload).status_code
            == 403
        )
        report = client.post(path, headers=headers(), json=payload)
        assert report.status_code == 200, report.text
        body = report.json()
        assert body["status"] == "uncertain" and body["report"]["analysis_status"] == "uncertain"
        assert len(body["report"]["affected_scene_ids"]) == 2
        assert any("Updated original wording" in str(item["after"]) for item in body["differences"])
        assert all(
            value in {decision.decision_id for decision in run.review_decisions}
            for value in body["report"]["reusable_decision_ids"]
        )
        unchanged = client.get(f"/api/v1/runs/{run_id}", headers=headers()).json()
        assert unchanged == current
        stale = client.post(
            path,
            headers=headers(),
            json={
                "before_ref": after["reference"],
                "after_ref": before.reference.model_dump(mode="json"),
            },
        )
        assert stale.status_code == 409
        forged = {**after["reference"], "sha256": "0" * 64}
        assert (
            client.post(path, headers=headers(), json={**payload, "after_ref": forged}).status_code
            == 404
        )


def test_diff_preserves_scalar_types_and_reports_truncation() -> None:
    differences, truncated = ChangeImpactService.differences({"flag": False}, {"flag": 0})
    assert len(differences) == 1 and not truncated
    differences, truncated = ChangeImpactService.differences({"removed": None}, {"added": None})
    assert {item.json_pointer for item in differences} == {"/removed", "/added"}
    assert not truncated
    differences, truncated = ChangeImpactService.differences(
        list(range(300)), list(range(300, 600))
    )
    assert len(differences) == 200 and truncated
