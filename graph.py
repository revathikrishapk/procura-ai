from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agents.state import ProcurementState
from app.agents.nodes import (
    intake_agent,
    sourcing_agent,
    negotiation_agent,
    approval_agent,
    purchase_order_agent,
    tracking_agent
)

def check_intake(state: ProcurementState) -> str:
    if not state.get("intake_valid", False):
        return "invalid"
    return "valid"

def should_pause(state: ProcurementState) -> str:
    if state.get("approval_required") and state.get("approved") is None:
        return "pause"
    if state.get("approved") is False:
        return "rejected"
    return "continue"

def create_workflow():
    workflow = StateGraph(ProcurementState)

    workflow.add_node("intake", intake_agent)
    workflow.add_node("sourcing", sourcing_agent)
    workflow.add_node("negotiation", negotiation_agent)
    workflow.add_node("approval", approval_agent)
    workflow.add_node("po_generation", purchase_order_agent)
    workflow.add_node("tracking", tracking_agent)

    workflow.set_entry_point("intake")

    workflow.add_conditional_edges("intake", check_intake, {"invalid": END, "valid": "sourcing"})
    workflow.add_edge("sourcing", "negotiation")
    workflow.add_edge("negotiation", "approval")

    workflow.add_conditional_edges(
        "approval",
        should_pause,
        {
            "pause": END,
            "rejected": END,
            "continue": "po_generation"
        }
    )

    workflow.add_edge("po_generation", "tracking")
    workflow.add_edge("tracking", END)
    
    return workflow