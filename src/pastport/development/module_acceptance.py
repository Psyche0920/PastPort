"""Run the offline F9 acceptance kit with replaceable trusted local factories."""

import argparse
import asyncio
import contextlib
import hashlib
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from contextlib import AbstractContextManager, ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from pastport.adapters.resources import LocalResourceReader
from pastport.application.models import LocalExecutionPolicy
from pastport.development.acceptance_models import (
    AcceptanceCase,
    AcceptanceCheck,
    AcceptanceReport,
    CaseName,
    FixtureFile,
)
from pastport.development.acceptance_scenario import scenario
from pastport.development.module_check import ModuleChecker
from pastport.ports.modules import EvidencePort, NarrativePort
from pastport.ports.resources import ResourceReader

REFERENCE_EVIDENCE = "pastport.development.reference_modules:build_evidence"
REFERENCE_NARRATIVE = "pastport.development.reference_modules:build_narrative"
CASES: tuple[CaseName, ...] = (
    "evidence_smoke",
    "narrative_smoke",
    "local_local",
    "selected_local",
    "local_selected",
    "selected_selected",
)


class FactoryLoader:
    """Load only developer-selected code; context-managed products close deterministically."""

    @staticmethod
    def load(specification: str, fixtures: Path, stack: ExitStack) -> object:
        module, separator, name = specification.partition(":")
        if (
            not separator
            or not all(part.isidentifier() for part in module.split("."))
            or not name.isidentifier()
        ):
            raise ValueError("Factory must be module:function")
        factory: object = getattr(importlib.import_module(module), name)
        if not callable(factory):
            raise TypeError("Factory must be callable")
        adapter: object = factory(fixtures)
        if isinstance(adapter, AbstractContextManager):
            adapter = stack.enter_context(adapter)
        return adapter

    @staticmethod
    def require(adapter: object, methods: Sequence[str]) -> None:
        if any(not callable(getattr(adapter, name, None)) for name in methods):
            raise TypeError("Factory product is missing port methods")


def fixture_identity(directory: Path) -> tuple[FixtureFile, ...]:
    """Hash a bounded local input tree without following symlinks."""
    entries: list[FixtureFile] = []
    size = 0
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Fixture symlinks are not supported")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Fixture inputs must be regular files")
        size += path.stat().st_size
        if len(entries) >= 512 or size > 64 * 1024 * 1024:
            raise ValueError("Fixture tree exceeds acceptance limits")
        entries.append(
            FixtureFile(
                relative_path=path.relative_to(directory).as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    if not entries:
        raise ValueError("Fixture directory is empty")
    return tuple(entries)


def worker(
    name: CaseName,
    fixtures: Path,
    directory: Path,
    timeout: float,
    evidence_factory: str,
    narrative_factory: str,
    resource_factory: str | None,
) -> AcceptanceCase:
    with ExitStack() as stack:
        evidence: EvidencePort | None = None
        narrative: NarrativePort | None = None
        if name in ("evidence_smoke", "selected_local", "selected_selected"):
            evidence_object = FactoryLoader.load(evidence_factory, fixtures, stack)
            FactoryLoader.require(evidence_object, ("inventory", "index", "research"))
            evidence = cast(EvidencePort, evidence_object)
        if name in ("narrative_smoke", "local_selected", "selected_selected"):
            narrative_object = FactoryLoader.load(narrative_factory, fixtures, stack)
            FactoryLoader.require(narrative_object, ("discover", "draft", "revise", "review"))
            narrative = cast(NarrativePort, narrative_object)
        checker = ModuleChecker(fixtures, timeout)
        if name in ("evidence_smoke", "narrative_smoke"):
            if name == "evidence_smoke":
                assert evidence is not None
                checks = asyncio.run(checker.evidence(evidence))
            else:
                assert narrative is not None
                checks = asyncio.run(checker.narrative(narrative))
            return AcceptanceCase(
                name=name,
                status="passed" if all(item.passed for item in checks) else "failed",
                checks=tuple(
                    AcceptanceCheck(
                        operation=item.operation, passed=item.passed, detail=item.detail
                    )
                    for item in checks
                ),
                detail="Independent DTO/project/cancellation smoke checks",
            )
        resources: ResourceReader = LocalResourceReader(fixtures, fixture_projects=True)
        if resource_factory is not None:
            resource_object = FactoryLoader.load(resource_factory, fixtures, stack)
            FactoryLoader.require(resource_object, ("read",))
            resources = cast(ResourceReader, resource_object)
        return scenario(name, fixtures, directory, timeout, evidence, narrative, resources)


class AcceptanceRunner:
    def __init__(
        self,
        fixtures: Path,
        evidence_factory: str,
        narrative_factory: str,
        resource_factory: str | None,
        timeout: float,
        case_timeout: float,
        evidence_version: str = "unreported",
        narrative_version: str = "unreported",
        resource_version: str = "unreported",
    ) -> None:
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Operation timeout must be greater than 0 and at most 60 seconds")
        if not math.isfinite(case_timeout) or not timeout <= case_timeout <= 300:
            raise ValueError(
                "Case timeout must cover the operation timeout and be at most 300 seconds"
            )
        self.fixtures = fixtures.resolve()
        self.evidence_factory = evidence_factory
        self.narrative_factory = narrative_factory
        self.resource_factory = resource_factory
        self.timeout = timeout
        self.case_timeout = case_timeout
        self.evidence_version = evidence_version
        self.narrative_version = narrative_version
        self.resource_version = resource_version

    def case(self, name: CaseName, fixtures: Path, directory: Path) -> AcceptanceCase:
        command = [
            sys.executable,
            "-m",
            "pastport.development.module_acceptance",
            "--worker-case",
            name,
            "--fixtures",
            str(fixtures),
            "--timeout",
            str(self.timeout),
            "--evidence-factory",
            self.evidence_factory,
            "--narrative-factory",
            self.narrative_factory,
        ]
        if self.resource_factory:
            command.extend(("--resource-factory", self.resource_factory))
        # Use files so subprocess output cannot grow the parent's captured memory without limit.
        with (
            (directory / "worker.stdout").open("wb") as stdout,
            (directory / "worker.stderr").open("wb") as stderr,
        ):
            try:
                result = subprocess.run(
                    command, stdout=stdout, stderr=stderr, timeout=self.case_timeout, check=False
                )
            except subprocess.TimeoutExpired:
                return AcceptanceCase(name=name, status="failed", detail="CASE_TIMEOUT")
        path = directory / "worker.stdout"
        if path.stat().st_size > 1024 * 1024:
            return AcceptanceCase(name=name, status="failed", detail="WORKER_REPORT_TOO_LARGE")
        try:
            record = AcceptanceCase.model_validate_json(path.read_bytes())
        except ValidationError:
            return AcceptanceCase(name=name, status="failed", detail="INVALID_WORKER_REPORT")
        if record.name != name or (record.status == "passed") != (result.returncode == 0):
            return AcceptanceCase(name=name, status="failed", detail="WORKER_RESULT_MISMATCH")
        return record

    def run(self) -> AcceptanceReport:
        started = datetime.now(UTC)
        identity = fixture_identity(self.fixtures)
        results: list[AcceptanceCase] = []
        with tempfile.TemporaryDirectory(prefix="pastport-acceptance-") as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            shutil.copytree(self.fixtures, fixtures)
            if fixture_identity(fixtures) != identity:
                raise ValueError("Fixture snapshot changed while copying")
            # Workflow assembly must not depend on a prebuilt runtime template.
            (fixtures / "runtime.json").unlink(missing_ok=True)
            snapshot = fixture_identity(fixtures)
            for name in CASES:
                needed = {
                    "evidence_smoke": name in ("selected_local", "selected_selected"),
                    "narrative_smoke": name in ("local_selected", "selected_selected"),
                }
                if any(
                    item.status != "passed" and needed.get(item.name, False) for item in results
                ):
                    results.append(
                        AcceptanceCase(
                            name=name,
                            status="not_run",
                            detail="Required selected module smoke check failed",
                        )
                    )
                    continue
                directory = root / name
                directory.mkdir()
                result = self.case(name, fixtures, directory)
                if fixture_identity(fixtures) != snapshot:
                    results.append(
                        AcceptanceCase(name=name, status="failed", detail="FIXTURE_MUTATED")
                    )
                    results.extend(
                        AcceptanceCase(
                            name=remaining, status="not_run", detail="Fixture snapshot was modified"
                        )
                        for remaining in CASES[len(results) :]
                    )
                    break
                results.append(result)
        policy = LocalExecutionPolicy(environment="test")
        return AcceptanceReport(
            policy_version=policy.version,
            graph_version=policy.graph_version,
            started_at=started,
            finished_at=datetime.now(UTC),
            evidence_factory=self.evidence_factory,
            narrative_factory=self.narrative_factory,
            resource_factory=self.resource_factory or "bundled-local-resource-reader",
            evidence_version=self.evidence_version,
            narrative_version=self.narrative_version,
            resource_version=self.resource_version,
            fixture_files=identity,
            passed=all(item.status == "passed" for item in results),
            cases=tuple(results),
        )


def run(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/reference"))
    parser.add_argument("--evidence-factory", default=REFERENCE_EVIDENCE)
    parser.add_argument("--narrative-factory", default=REFERENCE_NARRATIVE)
    parser.add_argument("--resource-factory")
    parser.add_argument("--evidence-version", default="unreported")
    parser.add_argument("--narrative-version", default="unreported")
    parser.add_argument("--resource-version", default="unreported")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--case-timeout", type=float, default=60)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-case", choices=CASES, help=argparse.SUPPRESS)
    args = parser.parse_args(arguments)
    if args.worker_case:
        name = cast(CaseName, args.worker_case)
        try:
            with tempfile.TemporaryDirectory(prefix="pastport-acceptance-case-") as temporary:
                with (
                    open(os.devnull, "w") as sink,
                    contextlib.redirect_stdout(sink),
                    contextlib.redirect_stderr(sink),
                ):
                    result = worker(
                        name,
                        args.fixtures,
                        Path(temporary),
                        args.timeout,
                        args.evidence_factory,
                        args.narrative_factory,
                        args.resource_factory,
                    )
        except Exception as error:
            # Trusted adapter failures are diagnostics, not raw project/provider output.
            result = AcceptanceCase(name=name, status="failed", detail=type(error).__name__)
        print(result.model_dump_json())
        return 0 if result.status == "passed" else 1
    try:
        if args.output is not None and args.output.exists():
            raise FileExistsError("Acceptance reports are never overwritten")
        report = AcceptanceRunner(
            args.fixtures,
            args.evidence_factory,
            args.narrative_factory,
            args.resource_factory,
            args.timeout,
            args.case_timeout,
            args.evidence_version,
            args.narrative_version,
            args.resource_version,
        ).run()
        serialized = report.model_dump_json(indent=2)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(serialized + "\n")
        if args.output is None:
            print(serialized)
        else:
            print(
                json.dumps(
                    {
                        "passed": report.passed,
                        "report": str(args.output),
                        "cases": [
                            {"name": item.name, "status": item.status, "detail": item.detail}
                            for item in report.cases
                        ],
                    },
                    indent=2,
                )
            )
        return 0 if report.passed else 1
    except (OSError, ValueError) as error:
        print(json.dumps({"passed": False, "error": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
