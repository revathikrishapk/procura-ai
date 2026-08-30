from typing import Optional
from typing_extensions import TypedDict


class ProcurementState(TypedDict, total=False):
    raw_request: str
    item_name: str
    quantity: int
    max_budget: Optional[float]
    status: str