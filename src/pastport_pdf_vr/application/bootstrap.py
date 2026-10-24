"""Compose explicit replay with optional read-only legacy evidence import."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.adapters.legacy_replay import LegacyMaterials, LegacyReplayReader
from pastport_pdf_vr.adapters.tour import TourImporter
from pastport_pdf_vr.application.replay import ReplayImporter
from pastport_pdf_vr.domain.models import ProcessingLimits
from pastport_pdf_vr.domain.tour import ImportedTour
from pastport_pdf_vr.workflow.graph import (
    FixedStage,
    FixedWorkflow,
    StageCommand,
    StageJournal,
    StageOutput,
)


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class ImportTourStage:
    def __init__(self, project: str, path: Path, workspace: Path, limits: ProcessingLimits) -> None:
        self.project, self.path, self.workspace, self.limits = project, path, workspace, limits

    def execute(self, command: StageCommand) -> StageOutput:
        current_path = self.workspace / "tour.json"
        if current_path.exists():
            current = ImportedTour.model_validate_json(current_path.read_bytes())
            if current.source.project_id != self.project:
                raise ValueError("A replay workspace cannot be reused by another project")
        assets = LocalAssetStore(self.workspace / "assets")
        tour = TourImporter(assets).import_html(self.project, self.path, self.limits)
        atomic_write(self.workspace / "tour.json", tour.model_dump_json())
        return StageOutput(references=("tour:" + tour.source.asset.sha256,))


class ImportReplayStage:
    def __init__(
        self, project: str, report: Path, workspace: Path, materials: LegacyMaterials | None = None
    ) -> None:
        self.project, self.report, self.workspace = project, report, workspace
        self.materials = materials

    def execute(self, command: StageCommand) -> StageOutput:
        tour = ImportedTour.model_validate_json((self.workspace / "tour.json").read_bytes())
        repository = SQLiteEditorialRepository(self.workspace / "editorial.sqlite3")
        revision = ReplayImporter(repository).import_report(
            self.project, tour, self.report, self.materials
        )
        return StageOutput(
            references=(f"preview:{self.project}:{revision}",),
            gaps=("synthetic_replay_not_fresh_recognition",)
            + (() if self.materials else ("historical_text_not_imported",)),
        )


class ExportStage:
    def __init__(self, project: str, workspace: Path) -> None:
        self.project, self.workspace = project, workspace

    def execute(self, command: StageCommand) -> StageOutput:
        snapshot = SQLiteEditorialRepository(self.workspace / "editorial.sqlite3").snapshot(
            self.project
        )
        payload = snapshot.model_dump_json()
        digest = hashlib.sha256(payload.encode()).hexdigest()
        destination = self.workspace / "snapshots"
        destination.mkdir(exist_ok=True)
        path = destination / (digest + ".json")
        if not path.exists():
            atomic_write(path, payload)
        elif path.read_text() != payload:
            raise ValueError("Immutable snapshot hash collision or corruption")
        return StageOutput(references=("snapshot:" + digest,))


class ReplayWorkflow:
    def run(
        self,
        project: str,
        tour_path: Path,
        report_path: Path,
        workspace: Path,
        limits: ProcessingLimits,
        run_id: str,
        legacy_database: Path | None = None,
    ) -> tuple[StageOutput, ...]:
        workspace.mkdir(parents=True, exist_ok=True)
        if (
            tour_path.stat().st_size > limits.tour_max_expanded_bytes
            or report_path.stat().st_size > 4 * 1024 * 1024
        ):
            raise ValueError("Replay inputs exceed their size limits")
        digest = hashlib.sha256()
        for path in (tour_path, report_path):
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(limits.model_dump_json().encode())
        materials = (
            LegacyReplayReader(LocalAssetStore(workspace / "assets")).read(project, legacy_database)
            if legacy_database
            else None
        )
        if materials:
            digest.update(materials.model_dump_json().encode())
        workflow = FixedWorkflow(
            StageJournal(workspace / "stages.sqlite3"),
            (
                FixedStage("import_tour", ImportTourStage(project, tour_path, workspace, limits)),
                FixedStage(
                    "import_replay", ImportReplayStage(project, report_path, workspace, materials)
                ),
                FixedStage("export_snapshot", ExportStage(project, workspace)),
            ),
            "replay-v2",
        )
        return workflow.run(project, run_id, "input:" + digest.hexdigest())
