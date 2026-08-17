from typing import TypedDict, List, Optional, Dict, Any

class ProcurementState(TypedDict):
    run_id: str
    request: Dict[str, Any]       # Item, quantity, budget
    intake_valid: bool
    error_message: Optional[str]
    candidate_vendors: List[Dict[str, Any]]
    quotes: List[Dict[str, Any]]
    selected_quote: Optional[Dict[str, Any]]
    approval_required: bool
    approved: Optional[bool]
    approver_notes: Optional[str]
    purchase_order: Optional[Dict[str, Any]]
    tracking_status: List[str]
    current_step: str