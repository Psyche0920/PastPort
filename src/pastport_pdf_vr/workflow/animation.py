"""Typed LangGraph entrypoint for chaining labelled VR -> animation -> Story Agent."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pastport_pdf_vr.application.animation import (
    AnimationDelivery,
    AnimationRun,
    AnimationWorkflow,
)


class AnimationState(TypedDict):
    animation_request: AnimationRun
    animation_delivery: AnimationDelivery | None


class AnimationNode:
    def __init__(self, workflow: AnimationWorkflow) -> None:
        self._workflow = workflow

    def __call__(self, state: AnimationState) -> dict[str, AnimationDelivery]:
        return {"animation_delivery": self._workflow.run(state["animation_request"])}


def build_animation_graph(
    workflow: AnimationWorkflow,
) -> CompiledStateGraph[AnimationState, None, AnimationState, AnimationState]:
    graph = StateGraph(AnimationState)
    graph.add_node("animate_museum", AnimationNode(workflow))
    graph.add_edge(START, "animate_museum")
    graph.add_edge("animate_museum", END)
    return graph.compile()
