from langgraph.graph import START, END, StateGraph

from app.agents.state import ProcurementState
from app.agents.nodes import parse_request_node


def create_procurement_graph():
    builder = StateGraph(ProcurementState)

    builder.add_node(
        "parse_request",
        parse_request_node,
    )

    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", END)

    return builder.compile()