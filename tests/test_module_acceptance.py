"""Exercise the offline kit, rejection boundaries and isolated factory lifecycle."""

import json
from contextlib import ExitStack
from pathlib import Path

import pytest

from pastport.development.acceptance_models import AcceptanceReport
from pastport.development.module_acceptance import (
    CASES,
    REFERENCE_EVIDENCE,
    REFERENCE_NARRATIVE,
    AcceptanceRunner,
    FactoryLoader,
    fixture_identity,
    run,
)

FIXTURES = Path(__file__).parent / "fixtures/reference"


def runner(fixtures: Path = FIXTURES, evidence: str = REFERENCE_EVIDENCE) -> AcceptanceRunner:
    return AcceptanceRunner(fixtures, evidence, REFERENCE_NARRATIVE, None, 10, 60)


def test_kit_runs_all_four_real_workflow_combinations_and_smokes() -> None:
    before = fixture_identity(FIXTURES)
    report = runner().run()
    assert report.passed
    assert report.mode == "offline-synthetic"
    assert tuple(item.name for item in report.cases) == CASES
    assert report.contract_version == "0.1.0"
    assert (report.policy_version, report.graph_version) == ("local-4", "editorial-4")
    assert report.evidence_version == "unreported"
    assert all(item.status == "passed" for item in report.cases)
    assert len(report.cases[0].checks) == 6
    assert len(report.cases[1].checks) == 8
    for case in report.cases[2:]:
        assert case.run_id and case.release_id and case.runtime_ref
        assert case.review_gates == ("evidence", "narrative", "publication")
        assert {"draft_preview", "player_restore", "release_binding", "private_only"} <= {
            check.operation for check in case.checks
        }
    assert fixture_identity(FIXTURES) == before
    assert AcceptanceReport.model_validate_json(report.model_dump_json()) == report


def factory_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> str:
    module = tmp_path / "external_acceptance_factory.py"
    module.write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + ":" + str(Path("src").resolve()))
    return "external_acceptance_factory:build"


def test_failed_supplied_factory_is_not_replaced_and_its_private_text_is_hidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = factory_module(
        tmp_path,
        monkeypatch,
        """
def build(fixtures):
    print("PRIVATE_SOURCE_AND_PROVIDER_BODY")
    raise RuntimeError("PRIVATE_SOURCE_AND_PROVIDER_BODY")
""",
    )
    report = runner(evidence=factory).run()
    cases = {item.name: item for item in report.cases}
    assert not report.passed
    assert cases["evidence_smoke"].status == "failed"
    assert cases["evidence_smoke"].detail == "RuntimeError"
    assert cases["local_local"].status == "passed"
    assert cases["local_selected"].status == "passed"
    assert cases["selected_local"].status == "not_run"
    assert cases["selected_selected"].status == "not_run"
    assert "PRIVATE_SOURCE_AND_PROVIDER_BODY" not in report.model_dump_json()


def test_noncooperating_factory_is_bounded_by_worker_process_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = factory_module(
        tmp_path,
        monkeypatch,
        """
import time

def build(fixtures):
    (fixtures / "entered").write_text("entered")
    time.sleep(30)
""",
    )
    bounded = AcceptanceRunner(tmp_path, factory, REFERENCE_NARRATIVE, None, 0.1, 3)
    case = bounded.case("evidence_smoke", tmp_path, tmp_path)
    assert (tmp_path / "entered").exists()
    assert case.status == "failed" and case.detail == "CASE_TIMEOUT"


def test_context_managed_factory_closes_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = factory_module(
        tmp_path,
        monkeypatch,
        """
from contextlib import contextmanager

@contextmanager
def build(fixtures):
    try:
        yield object()
    finally:
        (fixtures / "closed").write_text("closed")
""",
    )
    # Use a distinct module name so a previous import cannot choose another fixture factory.
    path = tmp_path / "managed_acceptance_factory.py"
    path.write_text((tmp_path / "external_acceptance_factory.py").read_text())
    with pytest.raises(TypeError), ExitStack() as stack:
        product = FactoryLoader.load(factory.replace("external_", "managed_"), tmp_path, stack)
        FactoryLoader.require(product, ("inventory",))
    assert (tmp_path / "closed").read_text() == "closed"


def test_input_mutation_aborts_following_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = factory_module(
        tmp_path,
        monkeypatch,
        """
from pastport.development.reference_modules import build_evidence

def build(fixtures):
    (fixtures / "mutation.txt").write_text("changed")
    return build_evidence(fixtures)
""",
    )
    report = runner(evidence=factory).run()
    assert not report.passed
    assert report.cases[0].detail == "FIXTURE_MUTATED"
    assert all(item.status == "not_run" for item in report.cases[1:])
    assert not (FIXTURES / "mutation.txt").exists()


def test_existing_report_is_never_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "existing.json"
    destination.write_text("original")
    assert run(["--output", str(destination)]) == 2
    assert destination.read_text() == "original"
    assert json.loads(capsys.readouterr().out)["error"] == "FileExistsError"


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 61])
def test_invalid_timeout_is_rejected_before_execution(timeout: float) -> None:
    with pytest.raises(ValueError):
        AcceptanceRunner(FIXTURES, REFERENCE_EVIDENCE, REFERENCE_NARRATIVE, None, timeout, 60)


def test_fixture_symlinks_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "linked.txt").symlink_to(FIXTURES / "synthetic-source.txt")
    with pytest.raises(ValueError, match="symlinks"):
        fixture_identity(tmp_path)
