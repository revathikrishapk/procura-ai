from langgraph.graph import StateGraph, END
from app.agents.state import ProcurementState
from app.agents.nodes import (
    parse_request_node,
    sourcing_agent_node,
    vendor_approval_node,
    po_dispatch_node
)

def check_ambiguity(state: ProcurementState) -> str:
    # If constraints are missing, halt before going to sourcing
    if state.get("is_ambiguous"):
        return "await_human"
    return "sourcing"

def create_workflow():
    workflow = StateGraph(ProcurementState)

    workflow.add_node("parse_request", parse_request_node)
    workflow.add_node("sourcing_agent", sourcing_agent_node)
    workflow.add_node("vendor_approval", vendor_approval_node)
    workflow.add_node("po_dispatch", po_dispatch_node)

    workflow.set_entry_point("parse_request")

    workflow.add_conditional_edges(
        "parse_request",
        check_ambiguity,
        {
            "await_human": END,
            "sourcing": "sourcing_agent"
        }
    )

    workflow.add_edge("sourcing_agent", "vendor_approval")
    workflow.add_edge("vendor_approval", "po_dispatch")
    workflow.add_edge("po_dispatch", END)

    return workflow