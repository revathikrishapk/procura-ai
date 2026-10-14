from typing import Optional
from typing_extensions import TypedDict


class ProcurementState(TypedDict, total=False):
    raw_request: str
    item_name: str
    quantity: int
    max_budget: Optional[float]
    suppliers: list[dict[str, object]]
    quotations: list[dict[str, object]]
    selected_supplier: str
    recommended_total: float
    approval_required: bool
    purchase_order_number: str
    purchase_order_status: str
    status: str