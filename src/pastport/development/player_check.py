"""Run F7 shared-JS conformance and report actual full action-vector results."""

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pastport.development.player_contracts import DIRECTORY, generated
from pastport.domain.common import Contract, Identifier
from pastport.domain.game import ActionVector


class PlayerVectorResult(Contract):
    vector_id: Identifier
    status: Literal["passed"] = "passed"


class PlayerVectorReport(Contract):
    action_vectors: tuple[PlayerVectorResult, ...]


class PlayerRulesReport(Contract):
    status: Literal["rules_passed"] = "rules_passed"
    profile: Literal["t1a-single-task"] = "t1a-single-task"
    action_vectors: tuple[PlayerVectorResult, ...]
    persistence_checks: Literal["run pytest tests/test_player_runtime.py"] = (
        "run pytest tests/test_player_runtime.py"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    for name, content in generated().items():
        if (DIRECTORY / name).read_text() != content:
            raise SystemExit("Generated player contracts are stale: " + name)
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node.js >=22 is required; player checks were not run")
    root = Path(__file__).resolve().parents[3]
    tests = [
        root / "tests" / name for name in ("player-components.test.mjs", "player-runtime.test.mjs")
    ]
    if not all(path.is_file() for path in tests):
        raise SystemExit("Player component checks require a repository checkout")
    try:
        result = subprocess.run(
            [node, "--test", *(str(path) for path in tests)], cwd=root, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit("Player component checks could not complete") from error
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    try:
        execution = subprocess.run(
            [node, str(DIRECTORY / "vectors.mjs")],
            cwd=root,
            timeout=30,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit("Action vector report could not complete") from error
    if execution.returncode != 0:
        raise SystemExit("Action vectors failed; no passing report was produced")
    actual = PlayerVectorReport.model_validate_json(execution.stdout)
    expected_ids = tuple(
        ActionVector.model_validate_json(path.read_bytes()).vector_id
        for path in sorted((root / "tests" / "fixtures" / "reference").glob("vector-*.json"))
    )
    if (
        len(expected_ids) != 5
        or tuple(item.vector_id for item in actual.action_vectors) != expected_ids
    ):
        raise SystemExit("Expected actual results for all five frozen action vectors")
    report = PlayerRulesReport(action_vectors=actual.action_vectors)
    if options.report is not None:
        options.report.write_text(report.model_dump_json(indent=2) + "\n")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
