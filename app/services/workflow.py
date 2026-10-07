from enum import Enum
from typing import Any, TypedDict


class CaseState(str, Enum):
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    INTAKE_COMPLETE = "INTAKE_COMPLETE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    SUPPLIERS_SHORTLISTED = "SUPPLIERS_SHORTLISTED"
    QUOTES_REQUESTED = "QUOTES_REQUESTED"
    QUOTES_RECEIVED = "QUOTES_RECEIVED"
    QUOTE_ANALYZED = "QUOTE_ANALYZED"
    NEGOTIATION_DRAFTED = "NEGOTIATION_DRAFTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PO_GENERATED = "PO_GENERATED"
    DELIVERY_IN_PROGRESS = "DELIVERY_IN_PROGRESS"
    DELIVERED = "DELIVERED"
    CLOSED = "CLOSED"
    NO_MATCHING_OFFERS = "NO_MATCHING_OFFERS"
    SOURCING_FAILED = "SOURCING_FAILED"
    FAILED = "FAILED"


class ProcurementState(TypedDict, total=False):
    case_id: str
    company_id: str
    requested_by: str | None
    product_name: str
    description: str | None
    quantity: int
    budget: float
    currency: str
    status: str
    current_stage: str
    error: str
    intake_summary: str
    request_analysis: dict[str, Any]
    sourcing_method: str
    offers: list[dict[str, Any]]
    supplier_evaluations: list[dict[str, Any]]
    quote_comparison: list[dict[str, Any]]
    selected_offer: dict[str, Any]
    quote_ids: list[str]
    selected_quote_id: str
    approval_id: str
    negotiation_drafts: list[dict[str, Any]]
    decision: str
    approved_by: str
    approval_comment: str
    po_id: str
    delivery_id: str
    tracking_reference: str | None
    tracking_status: str
    tracking_provider: str
    errors: list[str]


class WorkflowEventData(TypedDict, total=False):
    case_id: str
    stage: str
    event_type: str
    details: dict[str, Any]
