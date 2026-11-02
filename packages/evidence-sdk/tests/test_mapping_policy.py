"""New candidate breadth cannot silently change a saved execution policy."""
from pathlib import Path
from pastport_evidence.application.prompting import load_semantic_prompt, resolve_prompt_profile


def test_new_workspace_uses_broader_mapping_and_keeps_policy_on_reopen(tmp_path: Path) -> None:
    assert resolve_prompt_profile(tmp_path).mapping == 'v3'
    (tmp_path/'codex-executions.sqlite3').touch()
    assert resolve_prompt_profile(tmp_path).mapping == 'v3'
    prompt = load_semantic_prompt('pdf_matching', 'v3')
    assert 'EVERY supplied recognized object' in prompt
    assert 'does not relax physical identity checks' in prompt


def test_legacy_workspace_retains_mapping_receipt_policy(tmp_path: Path) -> None:
    (tmp_path/'codex-executions.sqlite3').touch()
    assert resolve_prompt_profile(tmp_path).mapping == 'v2'
