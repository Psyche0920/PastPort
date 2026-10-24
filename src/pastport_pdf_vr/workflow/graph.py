"""Fixed LangGraph stages backed by authoritative transactional stage receipts."""

from __future__ import annotations

import fcntl
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from pastport_pdf_vr.domain.models import DomainModel, ProjectId, ResourceId


class StageOutput(DomainModel):
    references: tuple[ResourceId, ...]
    gaps: tuple[str, ...] = ()


class StageCommand(DomainModel):
    project_id: ProjectId
    run_id: ResourceId
    input_binding: ResourceId
    stage: str


class Stage(Protocol):
    def execute(self, command: StageCommand) -> StageOutput: ...


class StageNode(Protocol):
    def __call__(self, state: GraphState) -> dict[str, str]: ...


class GraphState(TypedDict):
    project_id: str
    run_id: str
    input_binding: str
    graph_version: str


class RecoveryRequired(RuntimeError):
    """A previous stage was interrupted and must be reconciled before redispatch."""


class RunConflict(ValueError):
    """A run ID was reused with changed inputs or a project is already running."""


@dataclass(frozen=True, slots=True)
class FixedStage:
    name: str
    service: Stage


class StageJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    project TEXT NOT NULL,run_id TEXT NOT NULL,binding TEXT NOT NULL,
                    graph_version TEXT NOT NULL,status TEXT NOT NULL,
                    PRIMARY KEY(project,run_id));
                CREATE TABLE IF NOT EXISTS pipeline_stages (
                    project TEXT NOT NULL,run_id TEXT NOT NULL,stage TEXT NOT NULL,
                    status TEXT NOT NULL,output TEXT,error_type TEXT,
                    PRIMARY KEY(project,run_id,stage));
            """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def bind(self, state: GraphState) -> None:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT binding,graph_version FROM pipeline_runs WHERE project=? AND run_id=?",
                (state["project_id"], state["run_id"]),
            ).fetchone()
            if row and row != (state["input_binding"], state["graph_version"]):
                raise RunConflict("Run ID already belongs to different inputs or graph version")
            db.execute(
                "INSERT OR IGNORE INTO pipeline_runs VALUES (?,?,?,?,?)",
                (
                    state["project_id"],
                    state["run_id"],
                    state["input_binding"],
                    state["graph_version"],
                    "running",
                ),
            )

    def execute(self, stage: FixedStage, state: GraphState) -> StageOutput:
        key = (state["project_id"], state["run_id"], stage.name)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status,output FROM pipeline_stages WHERE project=? AND "
                "run_id=? AND stage=?",
                key,
            ).fetchone()
            if row:
                if row[0] == "completed":
                    return StageOutput.model_validate_json(row[1])
                raise RecoveryRequired(
                    f"Stage {stage.name} is {row[0]}; reconcile its effects before resuming"
                )
            db.execute("INSERT INTO pipeline_stages VALUES (?,?,?,'running',NULL,NULL)", key)
        try:
            output = stage.service.execute(
                StageCommand(
                    project_id=key[0],
                    run_id=key[1],
                    input_binding=state["input_binding"],
                    stage=stage.name,
                )
            )
        except Exception as error:
            # The stage may already have dispatched a billable/irreversible operation.
            # Store only its class, mark uncertain, re-raise; never retry automatically.
            with self._connection() as db:
                db.execute(
                    "UPDATE pipeline_stages SET status='recovery_required',error_type=? "
                    "WHERE project=? AND run_id=? AND stage=?",
                    (type(error).__name__, *key),
                )
                db.execute(
                    "UPDATE pipeline_runs SET status='recovery_required' WHERE project=? "
                    "AND run_id=?",
                    key[:2],
                )
            raise
        with self._connection() as db:
            db.execute(
                "UPDATE pipeline_stages SET status='completed',output=? WHERE "
                "project=? AND run_id=? AND stage=?",
                (output.model_dump_json(), *key),
            )
        return output

    def complete(self, state: GraphState, has_gaps: bool) -> None:
        with self._connection() as db:
            db.execute(
                "UPDATE pipeline_runs SET status=? WHERE project=? AND run_id=?",
                (
                    "completed_with_gaps" if has_gaps else "completed",
                    state["project_id"],
                    state["run_id"],
                ),
            )

    def results(self, state: GraphState) -> tuple[StageOutput, ...]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT output FROM pipeline_stages WHERE project=? AND run_id=? AND "
                "status='completed' ORDER BY stage",
                (state["project_id"], state["run_id"]),
            ).fetchall()
            return tuple(StageOutput.model_validate_json(row[0]) for row in rows)


class FixedWorkflow:
    def __init__(self, journal: StageJournal, stages: tuple[FixedStage, ...], version: str) -> None:
        if not stages or len({stage.name for stage in stages}) != len(stages):
            raise ValueError("Fixed stage names must be nonempty and unique")
        self._journal, self._stages, self._version = journal, stages, version

    def run(self, project_id: str, run_id: str, input_binding: str) -> tuple[StageOutput, ...]:
        state: GraphState = {
            "project_id": project_id,
            "run_id": run_id,
            "input_binding": input_binding,
            "graph_version": self._version,
        }
        # A workspace has shared tour metadata, so its lock must cover every project.
        lock = self._journal.path.parent / "workflow.lock"
        with lock.open("a+b") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RunConflict("Another workflow owns this project") from error
            try:
                self._journal.bind(state)
                graph = StateGraph(GraphState)
                previous = START
                for stage in self._stages:
                    graph.add_node(stage.name, self._node(stage))
                    graph.add_edge(previous, stage.name)
                    previous = stage.name
                graph.add_edge(previous, END)
                graph.compile().invoke(state)
                results = self._journal.results(state)
                self._journal.complete(state, any(result.gaps for result in results))
                return results
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _node(self, stage: FixedStage) -> StageNode:
        def execute(state: GraphState) -> dict[str, str]:
            self._journal.execute(stage, state)
            return {}

        return execute
