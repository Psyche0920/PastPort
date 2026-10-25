"""Alternative typed LangGraph path alongside the original panorama animation node."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pastport_pdf_vr.application.stylization3d import Style3DWorkflow
from pastport_pdf_vr.domain.stylization3d import Style3DDelivery, Style3DRun


class Style3DState(TypedDict):
    style3d_request: Style3DRun
    style3d_delivery: Style3DDelivery | None


class Style3DNode:
    def __init__(self, workflow: Style3DWorkflow) -> None:
        self.workflow = workflow

    def __call__(self, state: Style3DState) -> dict[str, Style3DDelivery]:
        return {"style3d_delivery": self.workflow.run(state["style3d_request"])}


def build_style3d_graph(
    workflow: Style3DWorkflow,
) -> CompiledStateGraph[Style3DState, None, Style3DState, Style3DState]:
    graph = StateGraph(Style3DState)
    graph.add_node("stylize_scene3d", Style3DNode(workflow))
    graph.add_edge(START, "stylize_scene3d")
    graph.add_edge("stylize_scene3d", END)
    return graph.compile()
