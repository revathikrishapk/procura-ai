import pandas as pd
import random
import uuid
import datetime
from app.config import AUTO_APPROVE_THRESHOLD, MOCK_VENDORS_CSV
from app.agents.state import ProcurementState

def safe_node(func):
    """Decorator to catch failures gracefully inside agents."""
    def wrapper(state: ProcurementState) -> ProcurementState:
        try:
            return func(state)
        except Exception as e:
            state["error_message"] = f"Error in {func.__name__}: {str(e)}"
            state["current_step"] = "FAILED"
            return state
    return wrapper

@safe_node
def intake_agent(state: ProcurementState) -> ProcurementState:
    req = state["request"]
    if req["quantity"] <= 0 or req["max_budget"] <= 0:
        state["intake_valid"] = False
        state["error_message"] = f"Invalid quantity ({req['quantity']}) or budget (${req['max_budget']})."
        state["current_step"] = "Intake Failed"
    else:
        state["intake_valid"] = True
        state["current_step"] = "Intake Complete"
    return state

@safe_node
def sourcing_agent(state: ProcurementState) -> ProcurementState:
    if not state.get("intake_valid"):
        return state
        
    df = pd.read_csv(MOCK_VENDORS_CSV)
    item_query = state["request"]["item_name"].lower()
    
    matches = df[df["category"].str.lower().str.contains(item_query, na=False)]
    if matches.empty:
        matches = df.sample(min(3, len(df)))
        
    vendors = matches.head(4).to_dict(orient="records")
    state["candidate_vendors"] = vendors
    
    # Add reasoning rationale
    vendor_names = ", ".join([v["name"] for v in vendors])
    state["approver_notes"] = f"Sourcing Agent identified {len(vendors)} potential suppliers: {vendor_names} based on rating and category match."
    state["current_step"] = "Sourcing Complete"
    return state

@safe_node
def negotiation_agent(state: ProcurementState) -> ProcurementState:
    candidates = state.get("candidate_vendors", [])
    if not candidates:
        state["error_message"] = "No candidate vendors available for negotiation."
        return state
        
    qty = state["request"]["quantity"]
    quotes = []
    
    for v in candidates:
        discount = 0.05 if qty >= 20 else 0.0
        unit_price = v["unit_price"] * (1 - discount)
        total_price = unit_price * qty
        quotes.append({
            "vendor_id": v["vendor_id"],
            "vendor_name": v["name"],
            "unit_price": round(unit_price, 2),
            "total_price": round(total_price, 2),
            "delivery_days": random.randint(3, 7),
            "applied_discount": f"{int(discount * 100)}%"
        })
    
    # Rank quotes by total price
    quotes.sort(key=lambda x: x["total_price"])
    quotes[0]["selected"] = True
    
    state["quotes"] = quotes
    state["selected_quote"] = quotes[0]
    
    selected = quotes[0]
    state["approver_notes"] = (
        f"Negotiated best pricing with {selected['vendor_name']}. "
        f"Unit cost reduced to ${selected['unit_price']} with a {selected['applied_discount']} bulk discount. "
        f"Total evaluated cost: ${selected['total_price']} with estimated {selected['delivery_days']}-day delivery."
    )
    state["current_step"] = "Negotiation Complete"
    return state

@safe_node
def approval_agent(state: ProcurementState) -> ProcurementState:
    selected = state.get("selected_quote")
    if not selected:
        return state
        
    total_cost = selected["total_price"]
    budget = state["request"]["max_budget"]
    
    if total_cost > AUTO_APPROVE_THRESHOLD:
        state["approval_required"] = True
        if state.get("approved") is None:
            state["current_step"] = "Awaiting Human Approval"
            return state
    else:
        state["approval_required"] = False
        state["approved"] = True
        state["approver_notes"] = f"Auto-approved: Total cost (${total_cost}) is within the threshold of ${AUTO_APPROVE_THRESHOLD}."

    state["current_step"] = "Approval Processed"
    return state

@safe_node
def purchase_order_agent(state: ProcurementState) -> ProcurementState:
    if not state.get("approved"):
        state["current_step"] = "Rejected"
        return state
        
    quote = state["selected_quote"]
    po = {
        "po_number": f"PO-{uuid.uuid4().hex[:8].upper()}",
        "vendor_name": quote["vendor_name"],
        "item_name": state["request"]["item_name"],
        "quantity": state["request"]["quantity"],
        "unit_price": quote["unit_price"],
        "total_cost": quote["total_price"],
        "status": "ISSUED",
        "issued_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    state["purchase_order"] = po
    state["current_step"] = "PO Issued"
    return state

@safe_node
def tracking_agent(state: ProcurementState) -> ProcurementState:
    if not state.get("purchase_order"):
        return state
        
    po_num = state["purchase_order"]["po_number"]
    state["tracking_status"] = [
        f"Order {po_num} received by supplier",
        "Payment Escrow Confirmed",
        "Items packed and dispatched from primary warehouse",
        "Carrier assigned — estimated delivery in 3-5 business days"
    ]
    state["current_step"] = "Completed"
    return state