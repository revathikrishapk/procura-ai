from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProcurementRequest(BaseModel):
    request: str = Field(
        ...,
        min_length=3,
        examples=["I need 10 laptops under $15,000"],
    )


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)


class ProductCreate(BaseModel):
    company_id: int
    name: str = Field(..., min_length=2, max_length=255)
    category: str = Field(default="General")
    unit: str = Field(default="unit")


class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    contact_email: str | None = None
    country: str = Field(default="US")
    reliability_score: float = Field(default=0.8, ge=0.0, le=1.0)
    verification_score: float = Field(default=0.8, ge=0.0, le=1.0)


class SupplierOfferCreate(BaseModel):
    supplier_id: int
    product_id: int
    price: float = Field(..., gt=0)
    currency: str = Field(default="USD")
    lead_time_days: int = Field(default=7, ge=0)
    is_internal: bool = False
    source_url: str | None = None
    evidence_note: str | None = None


class ProcurementCaseCreate(BaseModel):
    company_id: int
    product_id: int
    quantity: int = Field(..., gt=0)
    budget: float = Field(..., gt=0)
    currency: str = Field(default="USD")
    requester_name: str = Field(..., min_length=2)
    notes: str | None = None


class ApprovalAction(BaseModel):
    approver_name: str = Field(..., min_length=2)
    decision: str = Field(default="approved")
    reason: str | None = None


class DeliveryUpdate(BaseModel):
    status: str = Field(...)
    updated_by: str = Field(default="system")
    notes: str | None = None


class DemoSeedResult(BaseModel):
    company_id: int
    product_id: int
    supplier_id: int
    offer_id: int
    case_id: int
    created_at: datetime


class WorkflowSummary(BaseModel):
    case_id: int
    status: str
    current_stage: str
    source_summary: dict
    evaluation_summary: dict
    approval: Optional[dict] = None
    purchase_order: Optional[dict] = None
    delivery: Optional[dict] = None