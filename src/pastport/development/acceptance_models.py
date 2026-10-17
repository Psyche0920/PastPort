"""Versioned development reports, separate from shared content and runtime contracts."""

from typing import Literal

from pydantic import AwareDatetime

from pastport.domain.common import ArtifactRef, Contract, Sha256, Text

CaseName = Literal[
    "evidence_smoke",
    "narrative_smoke",
    "local_local",
    "selected_local",
    "local_selected",
    "selected_selected",
]


class AcceptanceCheck(Contract):
    operation: str
    passed: bool
    detail: str


class AcceptanceCase(Contract):
    name: CaseName
    status: Literal["passed", "failed", "not_run"]
    checks: tuple[AcceptanceCheck, ...] = ()
    detail: str
    run_id: str | None = None
    release_id: str | None = None
    runtime_ref: ArtifactRef | None = None
    review_gates: tuple[str, ...] = ()


class FixtureFile(Contract):
    relative_path: str
    sha256: Sha256


class AcceptanceReport(Contract):
    report_version: Literal["f9-acceptance-1"] = "f9-acceptance-1"
    contract_version: Literal["0.1.0"] = "0.1.0"
    policy_version: str
    graph_version: str
    mode: Literal["offline-synthetic"] = "offline-synthetic"
    started_at: AwareDatetime
    finished_at: AwareDatetime
    evidence_factory: str
    narrative_factory: str
    resource_factory: str
    evidence_version: Text = "unreported"
    narrative_version: Text = "unreported"
    resource_version: Text = "unreported"
    fixture_files: tuple[FixtureFile, ...]
    excluded_input_files: tuple[str, ...] = ("runtime.json",)
    passed: bool
    cases: tuple[AcceptanceCase, ...]
    not_verified: tuple[str, ...] = (
        "Formal Weng/Mert module acceptance and joint integration",
        "Paid providers, actual billing, historical accuracy and media rights",
        "Human playtests, production publication and remote CI execution",
        "Fault gate is separate; run fault_acceptance and retain its report",
    )
