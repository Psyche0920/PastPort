"""Run fixed F9 fault gates and retain a safe, version-bound local test report."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime

from pastport.application.models import LocalExecutionPolicy
from pastport.domain.common import Contract, Sha256

SUITES = (
    "tests/test_f9_faults.py",
    "tests/test_reliability.py",
    "tests/test_operations.py",
    "tests/test_shared_execution.py",
)


class FaultCase(Contract):
    suite: str
    name: str
    status: Literal["passed", "failed", "skipped"]


class FaultReport(Contract):
    report_version: Literal["f9-faults-1"] = "f9-faults-1"
    contract_version: Literal["0.1.0"] = "0.1.0"
    policy_version: str
    graph_version: str
    mode: Literal["offline-synthetic"] = "offline-synthetic"
    started_at: AwareDatetime
    finished_at: AwareDatetime
    source_sha256: Sha256
    suites: tuple[str, ...]
    exit_code: int
    passed: bool
    source_unchanged: bool
    cases: tuple[FaultCase, ...]
    not_verified: tuple[str, ...] = (
        "Formal Weng/Mert implementations and real-material quality",
        "Paid provider behavior, actual billing and historical/media rights",
        "Human playtests, remote CI, production and power-loss durability",
    )


def source_identity(root: Path) -> str:
    files = sorted(
        path
        for directory in ("src", "tests", "skills")
        for path in (root / directory).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    manifest = [
        (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in files
    ]
    return hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()


def parse_cases(path: Path) -> tuple[FaultCase, ...]:
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Fault report exceeds size limit")
    tree = ET.parse(path)
    results = []
    for case in tree.iter("testcase"):
        status: Literal["passed", "failed", "skipped"] = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None:
            status = "skipped"
        results.append(
            FaultCase(suite=case.attrib["classname"], name=case.attrib["name"], status=status)
        )
    if not results:
        raise ValueError("Fault gate produced no test cases")
    return tuple(results)


def run(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        if args.output.exists():
            raise FileExistsError("Fault reports are never overwritten")
        root = Path(__file__).resolve().parents[3]
        started = datetime.now(UTC)
        identity = source_identity(root)
        with tempfile.TemporaryDirectory(prefix="pastport-faults-") as temporary:
            directory = Path(temporary)
            junit = directory / "junit.xml"
            with (directory / "pytest.log").open("wb") as logs:
                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            *SUITES,
                            "-p",
                            "no:cacheprovider",
                            "--junitxml=" + str(junit),
                        ],
                        cwd=root,
                        stdout=logs,
                        stderr=logs,
                        timeout=240,
                        check=False,
                        env={
                            **os.environ,
                            "LANGSMITH_TRACING": "false",
                            "LANGCHAIN_TRACING_V2": "false",
                        },
                    )
                except subprocess.TimeoutExpired:
                    print(json.dumps({"passed": False, "error": "FAULT_GATE_TIMEOUT"}))
                    return 1
            cases = parse_cases(junit)
        unchanged = source_identity(root) == identity
        policy = LocalExecutionPolicy(environment="test")
        passed = (
            result.returncode == 0 and unchanged and all(item.status == "passed" for item in cases)
        )
        report = FaultReport(
            policy_version=policy.version,
            graph_version=policy.graph_version,
            started_at=started,
            finished_at=datetime.now(UTC),
            source_sha256=identity,
            suites=SUITES,
            exit_code=result.returncode,
            passed=passed,
            source_unchanged=unchanged,
            cases=cases,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(report.model_dump_json(indent=2) + "\n")
        print(
            json.dumps(
                {
                    "passed": passed,
                    "tests": len(cases),
                    "report": str(args.output),
                    "source_unchanged": unchanged,
                }
            )
        )
        return 0 if passed else 1
    except (OSError, ValueError, ET.ParseError, KeyError) as error:
        print(json.dumps({"passed": False, "error": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
