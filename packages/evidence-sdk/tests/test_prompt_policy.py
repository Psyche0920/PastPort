"""Policy upgrades apply to new workspaces while old paid bindings remain pinned."""
from pathlib import Path

import pytest

from pastport_evidence.application.prompting import load_semantic_prompt,resolve_prompt_profile


def test_new_workspace_pins_historical_content_policy(tmp_path: Path) -> None:
    root=tmp_path/'new'
    profile=resolve_prompt_profile(root)
    assert profile.evidence=='v3'
    assert profile.photo=='v3'
    assert resolve_prompt_profile(root)==profile
    assert load_semantic_prompt('evidence_association',profile.evidence)


def test_existing_execution_workspace_keeps_prior_policy(tmp_path: Path) -> None:
    (tmp_path/'codex-executions.sqlite3').touch()
    profile=resolve_prompt_profile(tmp_path)
    assert profile.evidence=='v2'
    assert profile.photo=='v1'
    assert load_semantic_prompt('evidence_association','v2')
    assert resolve_prompt_profile(tmp_path)==profile


def test_unknown_policy_is_not_silently_substituted() -> None:
    with pytest.raises(ValueError):load_semantic_prompt('evidence_association','v99')
