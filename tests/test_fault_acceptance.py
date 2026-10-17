"""A saved fault gate must report failures, skips and empty suites honestly."""

from pathlib import Path

import pytest

from pastport.development.fault_acceptance import parse_cases, run


def test_junit_statuses_exclude_raw_source_and_provider_errors(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text("""<testsuites><testsuite>
      <testcase classname="faults" name="success"/>
      <testcase classname="faults" name="failure"><failure>PRIVATE BODY</failure></testcase>
      <testcase classname="faults" name="error"><error>SECRET</error></testcase>
      <testcase classname="faults" name="skipped"><skipped>PRIVATE REASON</skipped></testcase>
    </testsuite></testsuites>""")
    cases = parse_cases(path)
    assert [item.status for item in cases] == ["passed", "failed", "failed", "skipped"]
    assert "PRIVATE" not in "".join(item.model_dump_json() for item in cases)
    assert "SECRET" not in "".join(item.model_dump_json() for item in cases)
    path.write_text("<testsuites/>")
    with pytest.raises(ValueError, match="no test cases"):
        parse_cases(path)


def test_saved_fault_evidence_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text("original evidence")
    assert run(["--output", str(path)]) == 2
    assert path.read_text() == "original evidence"
