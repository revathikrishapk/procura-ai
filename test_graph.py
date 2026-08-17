from app.agents.graph import procurement_graph
import uuid

def test_workflow():
    print("--- 1. Testing Over-Threshold (Requires Approval) ---")
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "run_id": thread_id,
        "request": {"item_name": "laptops", "quantity": 50, "max_budget": 40000},
        "intake_valid": False,
        "error_message": None,
        "candidate_vendors": [],
        "quotes": [],
        "selected_quote": None,
        "approval_required": False,
        "approved": None,
        "approver_notes": None,
        "purchase_order": None,
        "tracking_status": [],
        "current_step": "Initialized"
    }

    # First Execution Run (Should pause at Approval)
    for event in procurement_graph.stream(initial_state, config):
        print("Event:", event)

    current_state = procurement_graph.get_state(config).values
    print("\nState after pause:", current_state.get("current_step"))
    assert current_state.get("approval_required") is True
    assert current_state.get("approved") is None
    print("✓ Paused successfully as expected!")

    # Resuming Run after Human Approval
    print("\n--- 2. Simulating Human Approval ---")
    procurement_graph.update_state(
        config,
        {"approved": True, "approver_notes": "Looks good, approved by Manager."}
    )

    # Continue execution passing None to resume from checkpoint
    for event in procurement_graph.stream(None, config):
        print("Event:", event)

    final_state = procurement_graph.get_state(config).values
    print("\nFinal State Step:", final_state.get("current_step"))
    assert final_state.get("purchase_order") is not None
    print("✓ Resumed and completed successfully!")

if __name__ == "__main__":
    test_workflow()