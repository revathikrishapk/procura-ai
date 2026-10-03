from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.case import ProcurementCase
from app.models.company import Company
from app.models.workflow_event import WorkflowEvent
from app.schemas.case import CaseCreate, CaseRead
from app.services.dependencies import get_workflow_graph
from app.services.langgraph_workflow import workflow_config, workflow_summary

router = APIRouter(prefix="/cases")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=CaseRead, status_code=201)
def create_case(
    case: CaseCreate,
    db: Session = Depends(get_db),
    graph=Depends(get_workflow_graph),
):
    company = db.get(Company, case.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    case_record = ProcurementCase(
        id=f"CASE-{uuid4().hex[:8].upper()}",
        company_id=case.company_id,
        requested_by=case.requested_by,
        product_name=case.product_name,
        quantity=case.quantity,
        description=case.description,
        budget=case.budget,
        currency=case.currency,
        status="REQUEST_SUBMITTED",
        current_stage="INTAKE",
    )
    db.add(case_record)
    db.commit()
    db.refresh(case_record)

    graph.invoke(
        {
            **case.model_dump(),
            "case_id": case_record.id,
            "status": "REQUEST_SUBMITTED",
            "current_stage": "INTAKE",
        },
        config=workflow_config(case_record.id),
    )
    db.refresh(case_record)
    return case_record


@router.get("", response_model=list[CaseRead])
def list_cases(db: Session = Depends(get_db)):
    return db.scalars(select(ProcurementCase).order_by(ProcurementCase.id)).all()


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.get(ProcurementCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/{case_id}/workflow")
def get_case_workflow(
    case_id: str,
    db: Session = Depends(get_db),
    graph=Depends(get_workflow_graph),
):
    case = db.get(ProcurementCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    summary = workflow_summary(graph, case_id)
    events = db.scalars(
        select(WorkflowEvent)
        .where(WorkflowEvent.case_id == case_id)
        .order_by(WorkflowEvent.created_at, WorkflowEvent.id)
    ).all()
    summary["history"] = [
        {
            "id": event.id,
            "stage": event.stage,
            "event_type": event.event_type,
            "details": event.details,
            "created_at": event.created_at,
        }
        for event in events
    ]
    return summary


@router.post("/{case_id}/source", response_model=CaseRead)
def retry_case_sourcing(
    case_id: str,
    db: Session = Depends(get_db),
    graph=Depends(get_workflow_graph),
):
    case = db.get(ProcurementCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in {"SOURCING_FAILED", "NO_MATCHING_OFFERS"}:
        raise HTTPException(
            status_code=409,
            detail="Only cases with failed or empty sourcing can be retried.",
        )

    graph.invoke(
        {
            "case_id": case.id,
            "company_id": case.company_id,
            "requested_by": case.requested_by,
            "product_name": case.product_name,
            "description": case.description,
            "quantity": case.quantity,
            "budget": case.budget,
            "currency": case.currency,
            "status": "REQUEST_SUBMITTED",
            "current_stage": "INTAKE",
        },
        config=workflow_config(case.id),
    )
    db.refresh(case)
    return case
