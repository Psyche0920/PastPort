"""Regression coverage for new Turkish plans through real SDK compilation."""
import asyncio
from pathlib import Path
import pytest
import test_story_plan as fixtures
from test_story_automation import material_fixture, ROOT
from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.domain.modules import NarrativeDraft


def test_english_turkish_plan_compiles_without_chinese_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        fixtures, "words",
        lambda en, zh: {"en": en, "tr": "Kayıtları inceleyin ve kanıta göre karar verin."},
    )
    provider = fixtures.PlanProvider()
    runner = StoryAutomationWorkflow(
        material_fixture(tmp_path / "inputs"),
        tmp_path / "out", ROOT / "skills", "Synthetic en/tr contract check", provider,
    )
    asyncio.run(runner.run())
    draft = NarrativeDraft.model_validate_json(
        (tmp_path / "out/narrative-draft.json").read_bytes()
    )
    assert {table.locale for table in draft.package.game.locales} == {"en", "tr"}
    english, turkish = sorted(draft.package.game.locales, key=lambda table: table.locale)
    assert {entry.key for entry in english.entries} == {entry.key for entry in turkish.entries}
