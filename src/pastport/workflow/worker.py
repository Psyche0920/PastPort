"""One durable local graph executor. Business records remain the authority at human gates."""

import fcntl
import logging
import threading
from pathlib import Path
from typing import Protocol, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from pastport.application.models import ServiceError
from pastport.application.updates import updated
from pastport.domain.workflow import NodeName
from pastport.workflow.stages import StageRunner

logger = logging.getLogger(__name__)
NODES: tuple[NodeName, ...] = (
    "register_project",
    "inventory_sources",
    "extract_candidates",
    "discover_story",
    "select_candidate",
    "research_evidence",
    "evidence_review",
    "draft_narrative",
    "narrative_review",
    "assemble_package",
    "validate_package",
    "publish_review",
    "publish_package",
)


class GraphState(TypedDict):
    run_id: str


class GraphNode(Protocol):
    def __call__(self, state: GraphState) -> GraphState: ...


class EditorialWorker:
    def __init__(self, stages: StageRunner, checkpoint_path: Path) -> None:
        self.stages = stages
        self.checkpoint_path = checkpoint_path
        self.stopping = threading.Event()
        self.ready = threading.Event()
        self.failure: BaseException | None = None

    def stop(self) -> None:
        self.stopping.set()

    def run(self) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (self.checkpoint_path.parent / "instance.lock").open("a") as lock_file:
                try:
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise ServiceError(
                        "INSTANCE_BUSY", "Another worker already owns this data directory", 503
                    ) from error
                try:
                    self._run_locked()
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
        except BaseException as error:
            self.failure = error
            self.ready.set()
            logger.error("worker_stopped", extra={"error_type": type(error).__name__})
            raise

    def _run_locked(self) -> None:
        database = self.stages.database
        database.initialize()
        database.bind_environment(self.stages.environment)
        database.recover_commands()
        self.stages.reconcile_releases()
        with SqliteSaver.from_conn_string(str(self.checkpoint_path)) as checkpointer:
            builder: StateGraph[GraphState, None, GraphState, GraphState] = StateGraph(
                GraphState, input_schema=GraphState, output_schema=GraphState
            )
            for node in NODES:
                builder.add_node(node, self._handler(node), input_schema=GraphState)
                builder.add_conditional_edges(node, self._next)
            builder.add_conditional_edges(START, self._next)
            graph = builder.compile(checkpointer=checkpointer)
            self.ready.set()
            while not self.stopping.is_set():
                command = database.claim_command()
                if command is None:
                    self.stopping.wait(0.05)
                    continue
                run = database.run(command.run_id)
                if run.state.status == "cancelled":
                    database.finish_command(command.command_id)
                    continue
                config: RunnableConfig = {
                    "configurable": {"thread_id": command.run_id},
                    "recursion_limit": 64,
                }
                try:
                    self.stages.validate_run(run)
                    checkpoint = graph.get_state(config)
                    if checkpoint.interrupts:
                        graph.invoke(Command(resume=True), config)
                    elif checkpoint.next:
                        graph.invoke(None, config)
                    else:
                        graph.invoke(GraphState(run_id=command.run_id), config)
                except Exception as error:
                    # Record safe structured context; no provider bodies or source text are logged.
                    self.stages.fail(command.run_id, error)
                database.finish_command(command.command_id)

    def _next(self, state: GraphState) -> str:
        run = self.stages.database.run(state["run_id"])
        if run.state.status not in ("queued", "running"):
            return END
        return run.state.node

    def _handler(self, node: NodeName) -> GraphNode:
        def execute(state: GraphState) -> GraphState:
            run_id = state["run_id"]
            database = self.stages.database
            run = database.run(run_id)
            if run.state.node != node or run.state.status == "cancelled":
                return state
            if node == "select_candidate":
                if run.selected_candidate is None and run.state.status != "needs_review":
                    database.save(
                        updated(
                            run,
                            state=updated(
                                run.state, revision=run.state.revision + 1, status="needs_review"
                            ),
                        ),
                        run.state.revision,
                        "Waiting for direction confirmation",
                    )
                interrupt({"kind": "candidate_selection", "run_id": run_id})
                run = database.run(run_id)
                if run.selected_candidate is None:
                    raise ServiceError(
                        "SELECTION_MISSING", "Resume cannot replace direction confirmation"
                    )
                database.save(
                    updated(
                        run,
                        state=updated(
                            run.state,
                            revision=run.state.revision + 1,
                            node="research_evidence",
                            status="running",
                        ),
                    ),
                    run.state.revision,
                    "Selected direction accepted",
                )
            elif node in ("evidence_review", "narrative_review", "publish_review"):
                gate = (
                    "evidence"
                    if node == "evidence_review"
                    else "narrative"
                    if node == "narrative_review"
                    else "publication"
                )
                if not any(request.gate == gate for request in run.review_requests):
                    self.stages.gate(run_id, gate)
                interrupt({"kind": gate, "run_id": run_id})
                current = database.run(run_id)
                if current.state.node != node or current.state.status != "running":
                    return state
                if not self.stages.gate(run_id, gate):
                    raise ServiceError("REVIEW_REQUIRED", "Resume cannot replace a valid review")
            else:
                self.stages.execute(run_id, node)
            return state

        return execute
