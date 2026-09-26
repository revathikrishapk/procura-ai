from enum import Enum
from dataclasses import dataclass
from typing import Dict, Set

class CaseState(str, Enum):
    REQUEST_SUBMITTED="REQUEST_SUBMITTED"
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
    PO_SENT = "PO_SENT"
    DELIVERY_IN_PROGRESS = "DELIVERY_IN_PROGRESS"
    DELIVERED = "DELIVERED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
ALLOWED_TRANSITIONS: Dict[CaseState, Set[CaseState]] = {
    CaseState.REQUEST_SUBMITTED: {
        CaseState.INTAKE_COMPLETE,
        CaseState.CLARIFICATION_REQUIRED,
        CaseState.FAILED,
    },
    CaseState.CLARIFICATION_REQUIRED: {
        CaseState.REQUEST_SUBMITTED,
        CaseState.FAILED,
    },
    CaseState.INTAKE_COMPLETE: {
        CaseState.SUPPLIERS_SHORTLISTED,
        CaseState.CLARIFICATION_REQUIRED,
        CaseState.FAILED,
    },
    CaseState.SUPPLIERS_SHORTLISTED: {
        CaseState.QUOTES_REQUESTED,
        CaseState.FAILED,
    },
    CaseState.QUOTES_REQUESTED: {
        CaseState.QUOTES_RECEIVED,
        CaseState.FAILED,
    },
    CaseState.QUOTES_RECEIVED: {
        CaseState.QUOTE_ANALYZED,
        CaseState.FAILED,
    },
    CaseState.QUOTE_ANALYZED: {
        CaseState.PENDING_APPROVAL,
        CaseState.FAILED,
    },
    CaseState.PENDING_APPROVAL: {
        CaseState.APPROVED,
        CaseState.REJECTED,
        CaseState.FAILED,
    },
    CaseState.APPROVED: {
        CaseState.PO_GENERATED,
        CaseState.FAILED,
    },
    CaseState.REJECTED: {
        CaseState.CLOSED,
    },
    CaseState.PO_GENERATED: {
        CaseState.PO_SENT,
        CaseState.FAILED,
    },
    CaseState.PO_SENT: {
        CaseState.DELIVERY_IN_PROGRESS,
        CaseState.FAILED,
    },
    CaseState.DELIVERY_IN_PROGRESS: {
        CaseState.DELIVERED,
        CaseState.FAILED,
    },
    CaseState.DELIVERED: {
        CaseState.CLOSED,
    },
    CaseState.CLOSED: set(),
    CaseState.FAILED: set(),
}


def can_transition(current_state: CaseState, next_state: CaseState) -> bool:
    return next_state in ALLOWED_TRANSITIONS.get(current_state, set())


def transition(current_state: CaseState, next_state: CaseState) -> CaseState:
    if not can_transition(current_state, next_state):
        raise ValueError(
            f"Invalid transition from {current_state} to {next_state}"
        )
    return next_state