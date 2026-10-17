"""Verify the standalone handoff checker rejects incorrect adapters without starting services."""

import asyncio
import json
from pathlib import Path

import pytest

from pastport.application.updates import updated
from pastport.development.module_check import FixtureResults, ModuleChecker, run
from pastport.domain.evidence import SourceManifestDraft
from pastport.domain.modules import InventoryRequest, ModuleResult
from pastport.ports.modules import ExecutionContext

FIXTURES = Path(__file__).parent / "fixtures/reference"


@pytest.mark.parametrize("module,count", [("evidence", 6), ("narrative", 8)])
def test_standalone_commands_check_every_entry(
    module: str, count: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run([module, "--fixtures", str(FIXTURES)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "offline-synthetic"
    assert len(report["checks"]) == count and report["passed"]


@pytest.mark.parametrize(
    "problem", ["wrong-project", "wrong-dto", "timeout", "ignores-cancel", "blocked"]
)
def test_bad_adapter_cannot_pass(problem: str) -> None:
    class Broken(FixtureResults):
        async def inventory(
            self, request: InventoryRequest, context: ExecutionContext
        ) -> ModuleResult[SourceManifestDraft]:
            if problem == "timeout":
                await asyncio.sleep(1)
            if problem == "ignores-cancel":
                return ModuleResult[SourceManifestDraft].model_validate_json(
                    (FIXTURES / "inventory-result.json").read_bytes()
                )
            output = await super().inventory(request, context)
            if problem == "wrong-dto":
                # Constructed Pydantic data still must be revalidated by the consumer.
                return ModuleResult[SourceManifestDraft].model_construct(
                    outcome="completed",
                    payload=None,
                    issues=(),
                    evidence_requests=(),
                    changed_ids=(),
                    reason="Intentionally invalid test result",
                )
            if problem == "blocked":
                return updated(output, outcome="blocked", payload=None)
            assert output.payload is not None
            return updated(output, payload=updated(output.payload, project_id="other-project"))

    checks = asyncio.run(ModuleChecker(FIXTURES, 0.02).evidence(Broken(FIXTURES)))
    assert not all(item.passed for item in checks)
    assert any(not item.passed for item in checks if item.operation.startswith("inventory:"))


def test_context_is_fresh_and_disallows_paid_work() -> None:
    context = ModuleChecker(FIXTURES).context("draft", False)
    assert context.metadata.deadline.timestamp() > 0
    assert context.metadata.allowed_tools == ()
    limits = context.metadata.remaining_limits
    assert (
        limits.model_requests,
        limits.input_tokens,
        limits.output_tokens,
        limits.search_requests,
        limits.fetch_requests,
        limits.cost_microusd,
    ) == (0, 0, 0, 0, 0, 0)


def test_invalid_fixture_or_factory_returns_configuration_failure(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert run(["evidence", "--fixtures", str(tmp_path)]) == 2
    assert not json.loads(capsys.readouterr().out)["passed"]
    assert run(["narrative", "--fixtures", str(FIXTURES), "--factory", "invalid-spec"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "ValueError"


def test_external_factory_is_exercised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "handoff_test_adapter.py").write_text(
        "from pastport.development.module_check import FixtureResults\n"
        "def build(directory):\n    return FixtureResults(directory)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert (
        run(["evidence", "--fixtures", str(FIXTURES), "--factory", "handoff_test_adapter:build"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["adapter"] == "handoff_test_adapter:build"
    assert len(report["checks"]) == 6


def test_review_context_contains_the_current_narrative_reference() -> None:
    from pastport.domain.common import CanonicalSerializer
    from pastport.domain.modules import NarrativeReviewRequest

    request = NarrativeReviewRequest.model_validate_json(
        (FIXTURES / "review-request.json").read_bytes()
    )
    context = ModuleChecker(FIXTURES).context("review", False, request)
    narrative = next(
        reference for reference in context.metadata.input_refs if reference.kind == "narrative"
    )
    assert narrative.sha256 == CanonicalSerializer.digest(request.narrative.package)
    assert context.metadata.execution_key == CanonicalSerializer.digest(request)
