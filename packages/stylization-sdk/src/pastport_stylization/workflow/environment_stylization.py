"""Two typed paths sharing the existing panorama animation implementation."""

from typing import Annotated, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pastport_matched_environment.domain.models import DomainModel
from pydantic import Field

from pastport_stylization.application.animation import (
    AnimationDelivery,
    AnimationRun,
    AnimationWorkflow,
)
from pastport_stylization.application.stylization3d_tour import (
    Style3DTourDelivery,
    Style3DTourRun,
    Style3DTourWorkflow,
)


class PanoramaStyleRequest(DomainModel):
    kind: Literal["panorama"] = "panorama"
    request: AnimationRun


class Scene3DTourStyleRequest(DomainModel):
    kind: Literal["scene3d"] = "scene3d"
    request: Style3DTourRun


StyleRequest = Annotated[
    PanoramaStyleRequest | Scene3DTourStyleRequest, Field(discriminator="kind")
]
StyleDelivery = AnimationDelivery | Style3DTourDelivery


class EnvironmentStyleState(TypedDict):
    request: StyleRequest
    delivery: StyleDelivery | None


class EnvironmentStylizationNode:
    def __init__(self, panorama: AnimationWorkflow, scene3d: Style3DTourWorkflow) -> None:
        self.panorama = panorama
        self.scene3d = scene3d

    def __call__(self, state: EnvironmentStyleState) -> dict[str, StyleDelivery]:
        request = state["request"]
        if request.kind == "panorama":
            return {"delivery": self.panorama.run(request.request)}
        return {"delivery": self.scene3d.run(request.request)}


def build_environment_stylization_graph(
    panorama: AnimationWorkflow,
    scene3d: Style3DTourWorkflow,
) -> CompiledStateGraph[EnvironmentStyleState, None, EnvironmentStyleState, EnvironmentStyleState]:
    graph = StateGraph(EnvironmentStyleState)
    graph.add_node("stylize_environment", EnvironmentStylizationNode(panorama, scene3d))
    graph.add_edge(START, "stylize_environment")
    graph.add_edge("stylize_environment", END)
    return cast(
        CompiledStateGraph[
            EnvironmentStyleState,
            None,
            EnvironmentStyleState,
            EnvironmentStyleState,
        ],
        graph.compile(),
    )
