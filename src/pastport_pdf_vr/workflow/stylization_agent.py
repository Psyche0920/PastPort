"""Independent LangGraph node; the agent owns its one-repair decision lifecycle."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pastport_pdf_vr.application.automatic_stylization import (
    AutomaticStyleDelivery,
    AutomaticStyleRun,
)
from pastport_pdf_vr.application.stylization_agent import EnvironmentStylizationAgent


class StylizationAgentState(TypedDict):
    request: AutomaticStyleRun
    delivery: AutomaticStyleDelivery | None


class StylizationAgentNode:
    def __init__(self, agent: EnvironmentStylizationAgent) -> None:
        self.agent = agent

    def __call__(self, state: StylizationAgentState) -> dict[str, AutomaticStyleDelivery]:
        return {"delivery": self.agent.run(state["request"])}


def build_stylization_agent_graph(
    agent: EnvironmentStylizationAgent,
) -> CompiledStateGraph[StylizationAgentState, None, StylizationAgentState, StylizationAgentState]:
    graph = StateGraph(StylizationAgentState)
    graph.add_node("environment_stylization_agent", StylizationAgentNode(agent))
    graph.add_edge(START, "environment_stylization_agent")
    graph.add_edge("environment_stylization_agent", END)
    return graph.compile()
