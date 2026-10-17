"""Run independent module smoke checks without an API, database or workflow worker."""

import argparse
import asyncio
import importlib
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from pastport.application.updates import updated
from pastport.domain.common import ArtifactRef, CanonicalSerializer, Contract
from pastport.domain.evidence import SourceIndexDraft, SourceManifestDraft
from pastport.domain.modules import (
    CandidateSetDraft,
    DiscoverRequest,
    DraftRequest,
    EvidenceFindings,
    IndexRequest,
    InventoryRequest,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ResearchRequest,
    ReviseRequest,
)
from pastport.domain.workflow import ExecutionMetadata
from pastport.ports.modules import EvidencePort, ExecutionContext, NarrativePort


class ModuleCheckCancelled(RuntimeError):
    """The test cancellation signal must propagate out of the module."""


@dataclass(frozen=True, slots=True)
class CheckCancellation:
    cancelled: bool

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ModuleCheckCancelled("Module check cancelled")


@dataclass(frozen=True, slots=True)
class CheckResult:
    operation: str
    passed: bool
    detail: str


class FixtureResults:
    """Return explicit synthetic wire examples, without pretending to generate content."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    async def result[T: Contract](
        self, operation: str, model: type[ModuleResult[T]], context: ExecutionContext
    ) -> ModuleResult[T]:
        context.cancellation.raise_if_cancelled()
        return model.model_validate_json(
            (self.directory / (operation + "-result.json")).read_bytes()
        )

    async def inventory(
        self, request: InventoryRequest, context: ExecutionContext
    ) -> ModuleResult[SourceManifestDraft]:
        return await self.result("inventory", ModuleResult[SourceManifestDraft], context)

    async def index(
        self, request: IndexRequest, context: ExecutionContext
    ) -> ModuleResult[SourceIndexDraft]:
        return await self.result("index", ModuleResult[SourceIndexDraft], context)

    async def research(
        self, request: ResearchRequest, context: ExecutionContext
    ) -> ModuleResult[EvidenceFindings]:
        return await self.result("research", ModuleResult[EvidenceFindings], context)

    async def discover(
        self, request: DiscoverRequest, context: ExecutionContext
    ) -> ModuleResult[CandidateSetDraft]:
        return await self.result("discover", ModuleResult[CandidateSetDraft], context)

    async def draft(
        self, request: DraftRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        return await self.result("draft", ModuleResult[NarrativeDraft], context)

    async def revise(
        self, request: ReviseRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeDraft]:
        return await self.result("revise", ModuleResult[NarrativeDraft], context)

    async def review(
        self, request: NarrativeReviewRequest, context: ExecutionContext
    ) -> ModuleResult[NarrativeReview]:
        return await self.result("review", ModuleResult[NarrativeReview], context)


class ModuleChecker:
    def __init__(self, directory: Path, timeout_seconds: float = 2.0) -> None:
        if not 0 < timeout_seconds <= 60:
            raise ValueError("Timeout must be greater than zero and at most 60 seconds")
        self.directory = directory
        self.timeout_seconds = timeout_seconds

    def context(
        self, operation: str, cancelled: bool, request: Contract | None = None
    ) -> ExecutionContext:
        metadata = ExecutionMetadata.model_validate_json(
            (self.directory / "execution-metadata.json").read_bytes()
        )
        limits = updated(
            metadata.remaining_limits,
            model_requests=0,
            input_tokens=0,
            output_tokens=0,
            search_requests=0,
            fetch_requests=0,
            cost_microusd=0,
            active_seconds=math.ceil(self.timeout_seconds),
        )
        references = self.input_references(request) if request is not None else metadata.input_refs
        metadata = updated(
            metadata,
            input_refs=references,
            execution_key=CanonicalSerializer.digest(request)
            if request is not None
            else metadata.execution_key,
            operation_id="module-check:" + operation,
            deadline=datetime.now(UTC) + timedelta(seconds=self.timeout_seconds),
            remaining_limits=limits,
            allowed_tools=(),
        )
        return ExecutionContext(metadata, CheckCancellation(cancelled))

    @staticmethod
    def input_references(request: Contract) -> tuple[ArtifactRef, ...]:
        references: dict[tuple[str, str, str], ArtifactRef] = {}

        def collect(value: object) -> None:
            if isinstance(value, ArtifactRef):
                references[(value.artifact_id, value.content_version, value.sha256)] = value
            elif isinstance(value, Contract):
                for field in type(value).model_fields:
                    collect(getattr(value, field))
            elif isinstance(value, tuple):
                for item in value:
                    collect(item)

        collect(request)
        if isinstance(request, DiscoverRequest):
            reference = CanonicalSerializer.reference(
                request.index, "module-check-index", "source_index"
            )
            collect(reference)
        if isinstance(request, NarrativeReviewRequest):
            reference = CanonicalSerializer.reference(
                request.narrative.package, "module-check-narrative", "narrative"
            )
            collect(reference)
        return tuple(references.values())

    async def operation[Request: Contract, Payload: Contract](
        self,
        name: str,
        request_model: type[Request],
        result_model: type[ModuleResult[Payload]],
        invoke: Callable[[Request, ExecutionContext], Awaitable[ModuleResult[Payload]]],
    ) -> tuple[CheckResult, ...]:
        request = request_model.model_validate_json(
            (self.directory / (name + "-request.json")).read_bytes()
        )
        results = []
        for cancelled in (False, True):
            label = name + (":cancel" if cancelled else ":completed")
            context = self.context(name, cancelled, request)
            try:
                output = await asyncio.wait_for(invoke(request, context), self.timeout_seconds)
                if cancelled:
                    results.append(CheckResult(label, False, "Cancellation was not propagated"))
                    continue
                # Require the declared boundary type, then revalidate even constructed instances.
                expected = result_model
                if not isinstance(output, expected):
                    results.append(CheckResult(label, False, "Incorrect result DTO type"))
                    continue
                checked = expected.model_validate_json(output.model_dump_json())
                if checked.outcome != "completed" or checked.payload is None:
                    results.append(
                        CheckResult(
                            label,
                            False,
                            "Synthetic happy path did not complete: " + checked.outcome,
                        )
                    )
                    continue
                payload = checked.payload
                project = (
                    payload.package.project_id
                    if isinstance(payload, NarrativeDraft)
                    else payload.narrative_ref.project_id
                    if isinstance(payload, NarrativeReview)
                    else getattr(payload, "project_id", None)
                )
                if project != context.metadata.project_id:
                    results.append(CheckResult(label, False, "Output belongs to another project"))
                    continue
                if any(item.project_id != project for item in checked.evidence_requests):
                    results.append(
                        CheckResult(label, False, "Evidence request belongs to another project")
                    )
                    continue
                results.append(
                    CheckResult(
                        label, True, "Typed result, project identity and JSON roundtrip passed"
                    )
                )
            except (ModuleCheckCancelled, asyncio.CancelledError):
                results.append(
                    CheckResult(
                        label,
                        cancelled,
                        "Cancellation propagated" if cancelled else "Unexpected cancellation",
                    )
                )
            except Exception as error:
                # Adapter exceptions are reported by safe type, without source bodies.
                results.append(CheckResult(label, False, type(error).__name__))
        return tuple(results)

    async def evidence(self, port: EvidencePort) -> tuple[CheckResult, ...]:
        return (
            *await self.operation(
                "inventory", InventoryRequest, ModuleResult[SourceManifestDraft], port.inventory
            ),
            *await self.operation(
                "index", IndexRequest, ModuleResult[SourceIndexDraft], port.index
            ),
            *await self.operation(
                "research", ResearchRequest, ModuleResult[EvidenceFindings], port.research
            ),
        )

    async def narrative(self, port: NarrativePort) -> tuple[CheckResult, ...]:
        return (
            *await self.operation(
                "discover", DiscoverRequest, ModuleResult[CandidateSetDraft], port.discover
            ),
            *await self.operation("draft", DraftRequest, ModuleResult[NarrativeDraft], port.draft),
            *await self.operation(
                "revise", ReviseRequest, ModuleResult[NarrativeDraft], port.revise
            ),
            *await self.operation(
                "review", NarrativeReviewRequest, ModuleResult[NarrativeReview], port.review
            ),
        )


def run(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", choices=("evidence", "narrative"))
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/reference"))
    parser.add_argument(
        "--factory", help="Trusted offline factory module:function accepting the fixture Path"
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(arguments)
    try:
        checker = ModuleChecker(args.fixtures, args.timeout)
        adapter: object = FixtureResults(args.fixtures)
        if args.factory:
            module_name, separator, factory_name = args.factory.partition(":")
            if (
                not separator
                or not module_name
                or not factory_name
                or not factory_name.isidentifier()
            ):
                raise ValueError("Factory must be module:function")
            factory: object = getattr(importlib.import_module(module_name), factory_name)
            if not callable(factory):
                raise TypeError("Factory is not callable")
            adapter = factory(args.fixtures)
        module: Literal["evidence", "narrative"] = args.module
        methods = (
            ("inventory", "index", "research")
            if module == "evidence"
            else ("discover", "draft", "revise", "review")
        )
        if any(not callable(getattr(adapter, name, None)) for name in methods):
            raise TypeError("Adapter is missing required methods")
        checks = asyncio.run(
            checker.evidence(cast(EvidencePort, adapter))
            if module == "evidence"
            else checker.narrative(cast(NarrativePort, adapter))
        )
        print(
            json.dumps(
                {
                    "module": module,
                    "contract_version": "0.1.0",
                    "mode": "offline-synthetic",
                    "adapter": args.factory or "bundled-fixture-results",
                    "passed": all(item.passed for item in checks),
                    "checks": [
                        {"operation": item.operation, "passed": item.passed, "detail": item.detail}
                        for item in checks
                    ],
                },
                indent=2,
            )
        )
        return 0 if all(item.passed for item in checks) else 1
    except (OSError, ValueError, ImportError, AttributeError, TypeError, ValidationError) as error:
        print(json.dumps({"passed": False, "error": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
