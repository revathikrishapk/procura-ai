from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.schemas.approval import ApprovalCreate, ApprovalDecision, ApprovalRead
from app.services.procurement_workflow import generate_purchase_order

router = APIRouter(prefix="/approvals")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=ApprovalRead, status_code=201)
def create_approval(approval: ApprovalCreate, db: Session = Depends(get_db)):
    case = db.get(ProcurementCase, approval.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.company_id != approval.company_id:
        raise HTTPException(status_code=409, detail="Approval company must match the case.")

    approval_record = Approval(
        id=f"APP-{uuid4().hex[:8].upper()}",
        case_id=approval.case_id,
        company_id=approval.company_id,
        requested_by=approval.requested_by,
        approved_by=approval.approved_by,
        amount=approval.amount,
        currency=approval.currency,
        status="PENDING",
        comments=approval.comments,
    )
    db.add(approval_record)
    db.commit()
    db.refresh(approval_record)
    return approval_record


@router.get("", response_model=list[ApprovalRead])
def list_approvals(db: Session = Depends(get_db)):
    return db.scalars(select(Approval).order_by(Approval.id)).all()


@router.patch("/{approval_id}/approve", response_model=ApprovalRead)
def approve_approval(
    approval_id: str,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
):
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "PENDING":
        raise HTTPException(status_code=409, detail="Approval has already been decided")

    approval.status = "APPROVED"
    approval.approved_by = decision.approved_by
    approval.comments = decision.comments or approval.comments
    generate_purchase_order(db, approval)
    db.commit()
    db.refresh(approval)
    return approval


@router.patch("/{approval_id}/reject", response_model=ApprovalRead)
def reject_approval(
    approval_id: str,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
):
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "PENDING":
        raise HTTPException(status_code=409, detail="Approval has already been decided")

    approval.status = "REJECTED"
    approval.approved_by = decision.approved_by
    approval.comments = decision.comments or approval.comments
    case = db.get(ProcurementCase, approval.case_id)
    if case:
        case.status = "REJECTED"
        case.current_stage = "REJECTED"
    db.commit()
    db.refresh(approval)
    return approval
