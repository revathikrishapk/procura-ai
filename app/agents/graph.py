from langgraph.graph import START, END, StateGraph

from app.agents.state import ProcurementState
from app.agents.nodes import (
    analyze_quotations_node,
    evaluate_suppliers_node,
    parse_request_node,
    request_approval_node,
    source_suppliers_node,
)


def create_procurement_graph():
    builder = StateGraph(ProcurementState)

    builder.add_node(
        "parse_request",
        parse_request_node,
    )
    builder.add_node("source_suppliers", source_suppliers_node)
    builder.add_node("evaluate_suppliers", evaluate_suppliers_node)
    builder.add_node("analyze_quotations", analyze_quotations_node)
    builder.add_node("request_approval", request_approval_node)

    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", "source_suppliers")
    builder.add_edge("source_suppliers", "evaluate_suppliers")
    builder.add_edge("evaluate_suppliers", "analyze_quotations")
    builder.add_edge("analyze_quotations", "request_approval")
    builder.add_edge("request_approval", END)

    return builder.compile()