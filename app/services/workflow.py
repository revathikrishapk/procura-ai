from enum import Enum
from typing import TypedDict, Any


class CaseState(str, Enum):
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    INTAKE_COMPLETE = "INTAKE_COMPLETE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"

    SUPPLIERS_SHORTLISTED = "SUPPLIERS_SHORTLISTED"

    QUOTES_REQUESTED = "QUOTES_REQUESTED"
    QUOTES_RECEIVED = "QUOTES_RECEIVED"
    QUOTE_ANALYZED = "QUOTE_ANALYZED"

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

    PO_GENERATED = "PO_GENERATED"

    DELIVERY_IN_PROGRESS = "DELIVERY_IN_PROGRESS"
    DELIVERED = "DELIVERED"

    CLOSED = "CLOSED"
    FAILED = "FAILED"


class ProcurementState(TypedDict, total=False):

    case_id: str

    title: str
    description: str

    quantity: int
    budget: float

    status: str

    error: str

    intake_summary: str

    suppliers: list[dict[str, Any]]

    quotes: list[dict[str, Any]]

    selected_quote: dict[str, Any]

    selected_supplier: str

    approval_comment: str

    po_id: str

    tracking_reference: str