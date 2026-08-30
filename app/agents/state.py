from typing import TypedDict, Optional, List, Dict, Any

class ProcurementState(TypedDict):
    raw_request: str
    request_spec: Dict[str, Any]
    quotes: List[Dict[str, Any]]
    comparison: Dict[str, Any]
    is_ambiguous: bool
    missing_fields: List[str]
    human_clarification: Optional[str]
    manager_approved: Optional[bool]
    requires_manager_approval: Optional[bool]
    error: Optional[str]