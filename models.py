from pydantic import BaseModel, Field
from typing import Optional, List

class RequisitionRequest(BaseModel):
    item_name: str
    quantity: int
    max_budget: float
    requested_by: str = "Employee"

class Vendor(BaseModel):
    vendor_id: str
    name: str
    category: str
    rating: float
    unit_price: float

class Quote(BaseModel):
    vendor_id: str
    vendor_name: str
    unit_price: float
    total_price: float
    delivery_days: int
    selected: bool = False

class ApprovalDecision(BaseModel):
    required: bool
    approved: Optional[bool] = None
    approver: Optional[str] = None
    reason: Optional[str] = None

class PurchaseOrder(BaseModel):
    po_number: str
    vendor_name: str
    item_name: str
    quantity: int
    total_cost: float
    status: str

class TrackingEvent(BaseModel):
    stage: str
    message: str
    timestamp: str