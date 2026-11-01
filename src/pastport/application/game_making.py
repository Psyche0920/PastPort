"""Checkpointed Main orchestration; SDKs retain their own internal execution authority."""

import fcntl
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypedDict

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer, Contract, Sha256
from pastport.domain.game_making import GameMakingRequest, GameMakingResult
from pastport.ports.game_making import GameMakingStages


class _GraphState(TypedDict):
    run_directory: str


class _StageReceipt(Contract):
    stage: Literal["story", "gameplay", "presentation", "assembly"]
    artifact: Path
    sha256: Sha256


class _RunLock(Contract):
    request: Sha256
    stages: Sha256
    inputs: dict[str, Sha256]


class _ManifestFile(Contract):
    path: str
    sha256: Sha256
    size_bytes: int = Field(ge=0)


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    files: tuple[_ManifestFile, ...]


class GameMakingWorkflow:
    """Private, provider-disabled integration; no budget or approval is invented here."""

    def __init__(self, stages: GameMakingStages) -> None:
        self.stages = stages

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _cached(self, request: GameMakingRequest, stage: str) -> bool:
        path = request.output_directory / "receipts" / (stage + ".json")
        if not path.exists():
            return False
        receipt = _StageReceipt.model_validate_json(path.read_bytes())
        if (
            receipt.stage != stage
            or not receipt.artifact.resolve().is_relative_to(request.output_directory.resolve())
            or self._hash(receipt.artifact) != receipt.sha256
        ):
            raise ServiceError("GAME_ARTIFACT_CHANGED", "Saved stage output changed")
        return True

    def _record(self, request: GameMakingRequest, stage: str, artifact: Path) -> None:
        receipt = _StageReceipt.model_validate(
            {
                "stage": stage,
                "artifact": artifact,
                "sha256": self._hash(artifact),
            }
        )
        directory = request.output_directory / "receipts"
        directory.mkdir(exist_ok=True)
        (directory / (stage + ".json")).write_text(receipt.model_dump_json(indent=2))

    def _verify_manifest(self, request: GameMakingRequest) -> None:
        directory = request.output_directory / "game-3d"
        manifest = _Manifest.model_validate_json((directory / "manifest.json").read_bytes())
        for entry in manifest.files:
            path = (directory / entry.path).resolve()
            if not path.is_relative_to(directory.resolve()) or self._hash(path) != entry.sha256:
                raise ServiceError("GAME_RESOURCE_CHANGED", "Packaged resource integrity failed")

    async def run(self, request: GameMakingRequest) -> GameMakingResult:
        root = request.output_directory
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".game-making.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return await self._run_locked(request)

    async def _run_locked(self, request: GameMakingRequest) -> GameMakingResult:
        root = request.output_directory
        identities = _RunLock(
            request=CanonicalSerializer.digest(request),
            stages=self.stages.identity(),
            inputs={
                str(path): self._hash(path)
                for path in (
                    request.original_pdf,
                    request.source_document,
                    request.environment,
                    request.saved_story_run / "input-lock.json",
                    request.saved_story_run / "narrative-draft.json",
                    request.skills_directory / "narrative/SKILL.md",
                    request.museum_directory / "data/presentation.json",
                    request.museum_directory / "data/runtime.json",
                    request.museum_directory / "data/scene3d-input.json",
                )
            },
        )
        pinned = root / "input-lock.json"
        if pinned.exists() and _RunLock.model_validate_json(pinned.read_bytes()) != identities:
            raise ServiceError("GAME_INPUT_CHANGED", "Use a new run for changed inputs or SDKs")
        if not pinned.exists():
            pinned.write_text(identities.model_dump_json(indent=2) + "\n")
        # Receipts are rechecked even when the graph has reached END.
        for stage in ("story", "gameplay", "presentation", "assembly"):
            self._cached(request, stage)

        async def story(state: _GraphState) -> _GraphState:
            if not self._cached(request, "story"):
                self._record(request, "story", await self.stages.story(request))
            return state

        def local(
            stage: str, invoke: Callable[[GameMakingRequest], Path]
        ) -> Callable[[_GraphState], _GraphState]:
            def execute(state: _GraphState) -> _GraphState:
                if not self._cached(request, stage):
                    self._record(request, stage, invoke(request))
                return state

            return execute

        async with AsyncSqliteSaver.from_conn_string(
            str(root / "checkpoints.sqlite3")
        ) as checkpointer:
            builder: StateGraph[_GraphState, None, _GraphState, _GraphState] = StateGraph(
                _GraphState,
                input_schema=_GraphState,
                output_schema=_GraphState,
            )
            builder.add_node("story", story, input_schema=_GraphState)
            builder.add_node(
                "gameplay",
                RunnableLambda[_GraphState, _GraphState](local("gameplay", self.stages.gameplay)),
                input_schema=_GraphState,
            )
            builder.add_node(
                "presentation",
                RunnableLambda[_GraphState, _GraphState](
                    local("presentation", self.stages.presentation)
                ),
                input_schema=_GraphState,
            )
            builder.add_node(
                "assembly",
                RunnableLambda[_GraphState, _GraphState](local("assembly", self.stages.assembly)),
                input_schema=_GraphState,
            )
            for before, after in (
                (START, "story"),
                ("story", "gameplay"),
                ("gameplay", "presentation"),
                ("presentation", "assembly"),
                ("assembly", END),
            ):
                builder.add_edge(before, after)
            graph = builder.compile(checkpointer=checkpointer)
            await graph.ainvoke(
                _GraphState(run_directory=str(root)),
                {"configurable": {"thread_id": "private-game-trial"}},
            )
        self._verify_manifest(request)
        result = GameMakingResult(game_directory=root / "game-3d")
        (root / "result.json").write_text(result.model_dump_json(indent=2))
        return result
