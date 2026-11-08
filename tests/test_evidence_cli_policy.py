"""CLI accounting initialization must not misclassify new text-first workspaces."""

import sys
from pathlib import Path

import pytest
from pastport_evidence.application.photo_mapping import PhotoMappingWorkflow
from pastport_evidence.application.prompting import resolve_prompt_profile
from pastport_evidence.domain.execution import SubscriptionGrant


def test_cli_pins_new_policy_before_creating_usage_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pastport_evidence.cli import main

    workspace = tmp_path / "workspace"
    grant = tmp_path / "grant.json"
    grant.write_text(SubscriptionGrant(grant_ref="test", project_id="test").model_dump_json())

    def stopped(self: PhotoMappingWorkflow, *args: object, **kwargs: object) -> None:
        assert (workspace / "codex-executions.sqlite3").exists()
        assert resolve_prompt_profile(workspace).mapping == "text-v1"
        raise RuntimeError("TEST_STOP_BEFORE_DISPATCH")

    monkeypatch.setattr(PhotoMappingWorkflow, "run", stopped)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pastport-evidence",
            "--pdf",
            str(tmp_path / "source.pdf"),
            "--photos",
            str(tmp_path / "photos"),
            "--workspace",
            str(workspace),
            "--grant",
            str(grant),
            "--run-id",
            "test",
            "--no-token-threshold",
        ],
    )
    with pytest.raises(RuntimeError, match="TEST_STOP_BEFORE_DISPATCH"):
        main()
