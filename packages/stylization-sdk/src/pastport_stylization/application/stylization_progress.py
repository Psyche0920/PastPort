"""Read-only progress from actual execution receipts and saved Agent checkpoints."""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Literal

from pastport_matched_environment.application.storage import atomic_write
from pastport_matched_environment.domain.animation import AnimationImageResult
from pastport_matched_environment.domain.execution import ExecutionOutput
from pastport_matched_environment.domain.models import DomainModel
from pydantic import ConfigDict, Field, ValidationError

from pastport_stylization.domain.stylization_agent import StylizationAgentReport

FACES = ("front", "right", "back", "left", "up", "down")
Phase = Literal[
    "ready",
    "preparing",
    "planning",
    "generating",
    "assembling",
    "reviewing",
    "repairing",
    "reassembling",
    "final_review",
    "packaging",
    "completed",
    "attention",
    "unavailable",
]


class ProgressSource(DomainModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    kind: Literal["panorama", "scene3d"]
    viewpoints: int = Field(ge=1, le=16)


class ProgressJob(DomainModel):
    # Read only the progress projection; unrelated job fields retain their own validation.
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    run_id: str = Field(pattern="^[a-f0-9]{32}$")
    status: Literal["prepared", "running", "completed", "recovery_required"]
    execution: Literal["pipeline", "agent"] = "pipeline"
    source: ProgressSource


class ViewProgress(DomainModel):
    number: int
    completed_directions: tuple[str, ...]


class RunProgress(DomainModel):
    run_id: str
    phase: Phase
    round_number: Literal[0, 1] = 0
    images_done: int = 0
    images_total: int
    reviews_done: int = 0
    reviews_total: int = 0
    calls_done: int = 0
    call_in_flight: bool = False
    repair_skipped: bool = False
    elapsed_seconds: int = 0
    views: tuple[ViewProgress, ...] = ()


class ProgressSnapshot(DomainModel):
    generated_at: float
    runs: tuple[RunProgress, ...]


class StylizationProgressReader:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace.resolve() / "stylization"

    def snapshot(self) -> ProgressSnapshot:
        runs = []
        for path in self.root.glob("*/job.json"):
            try:
                job = ProgressJob.model_validate_json(path.read_bytes())
                runs.append(self._read(job, path.parent))
            except (OSError, ValueError, sqlite3.Error):
                if re.fullmatch("[a-f0-9]{32}", path.parent.name):
                    runs.append(
                        RunProgress(run_id=path.parent.name, phase="unavailable", images_total=0)
                    )
        return ProgressSnapshot(generated_at=time.time(), runs=tuple(runs))

    @staticmethod
    def _read(job: ProgressJob, folder: Path) -> RunProgress:
        output = folder / "output"
        ledger = output / "usage.sqlite3"
        if job.execution == "pipeline" and job.source.kind == "scene3d":
            ledger = output / "animation/usage.sqlite3"
        paths: set[Path] = set()
        completed, in_flight, uncertain = 0, False, False
        if ledger.is_file():
            with closing(
                sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            ) as db:
                rows = db.execute("SELECT state,result FROM executions").fetchall()
            for state, result in rows:
                completed += int(state == "completed")
                in_flight |= state == "dispatching"
                uncertain |= state == "recovery_required"
                if state != "completed" or result is None:
                    continue
                receipt = ExecutionOutput.model_validate_json(result)
                try:
                    image = AnimationImageResult.model_validate_json(receipt.payload_json)
                except ValidationError:
                    continue  # Semantic planning/review receipts are counted, not image directions.
                if image.status == "generated" and image.image_path:
                    path = Path(image.image_path).resolve()
                    if path.is_relative_to(output) and path.is_file():
                        paths.add(path)
        round_number: Literal[0, 1] = 1 if (output / "round-1-policy.txt").is_file() else 0
        round_root = output / f"round-{round_number}" if job.execution == "agent" else output
        if job.source.kind == "scene3d":
            round_root /= "animation"
        views = []
        for index in range(job.source.viewpoints):
            directory = round_root / f"view-{index:03d}"
            directions = tuple(
                face
                for face in FACES
                if any(p.parent == directory / f"generated-{face}" for p in paths)
            )
            views.append(ViewProgress(number=index + 1, completed_directions=directions))
        done = sum(len(v.completed_directions) for v in views)
        total = 6 * job.source.viewpoints
        review_total = 2 * job.source.viewpoints - 1 if job.execution == "agent" else 0
        reviews_done = sum(
            1 for i in range(review_total) if (output / f"review-{round_number}-{i}.json").is_file()
        )
        skipped = False
        if (output / "agent-report.json").is_file():
            report = StylizationAgentReport.model_validate_json(
                (output / "agent-report.json").read_bytes()
            )
            skipped = report.repair_rounds == 0
        phase: Phase
        if job.status == "completed":
            phase = "completed"
        elif job.status == "recovery_required" or uncertain:
            phase = "attention"
        elif job.status == "prepared":
            phase = "ready"
        elif (output / "agent-report.json").is_file():
            phase = "packaging"
        elif job.execution == "pipeline":
            phase = "generating" if done < total else "packaging"
        elif (output / f"round-{round_number}-delivery.json").is_file():
            phase = "final_review" if round_number else "reviewing"
        elif round_number:
            phase = "repairing" if done < total else "reassembling"
        elif (output / "plan.json").is_file():
            phase = "generating" if done < total else "assembling"
        elif (output / "plan-input.json").is_file():
            phase = "planning"
        else:
            phase = "preparing"
        attempt = folder / "run.json"
        elapsed = max(0, int(time.time() - attempt.stat().st_mtime)) if attempt.is_file() else 0
        if job.status != "running" and attempt.is_file():
            elapsed = max(0, int((folder / "job.json").stat().st_mtime - attempt.stat().st_mtime))
        return RunProgress(
            run_id=job.run_id,
            phase=phase,
            round_number=round_number,
            images_done=done,
            images_total=total,
            reviews_done=reviews_done,
            reviews_total=review_total,
            calls_done=completed,
            call_in_flight=in_flight,
            repair_skipped=skipped,
            elapsed_seconds=elapsed,
            views=tuple(views),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--max-seconds", type=int, default=86400)
    args = parser.parse_args()
    reader = StylizationProgressReader(args.workspace)
    destination = args.bridge.resolve()
    if ".runtime" not in destination.parts:
        parser.error("Progress bridge must be in an ignored .runtime directory")
    if args.parent_pid <= 1:
        parser.error("An owned parent service PID is required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + min(max(args.max_seconds, 1), 86400)
    print("Read-only progress bridge started; no workflow, provider or ledger writes.", flush=True)
    while time.monotonic() < deadline:
        try:
            os.kill(args.parent_pid, 0)
        except ProcessLookupError:
            break
        atomic_write(destination, reader.snapshot().model_dump_json())
        time.sleep(2)


if __name__ == "__main__":
    main()
