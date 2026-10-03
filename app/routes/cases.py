from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.models.company import Company
from app.models.quote import Quote
from app.models.supplier import Supplier
from app.schemas.case import CaseCreate, CaseRead
from app.services.database_service import find_internal_supplier_offers
from app.services.intake_agent import validate_case_request
from app.services.sourcing_agent import (
    SourcingError,
    choose_best_offer,
    search_external_suppliers,
)

router = APIRouter(prefix="/cases")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _create_quote_for_offer(
    db: Session,
    case_record: ProcurementCase,
    offer: dict,
    status: str,
):
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.company_id == case_record.company_id,
            Supplier.name == offer["supplier_name"],
        )
    )
    if not supplier:
        supplier = Supplier(
            id=f"SUP-{uuid4().hex[:8].upper()}",
            company_id=case_record.company_id,
            name=offer["supplier_name"],
            website=offer.get("source"),
            verification_status="UNVERIFIED",
            discovery_source=offer.get("source_type", "internal").upper(),
        )
        db.add(supplier)
        db.flush()

    source_notes = (
        f"Source: {offer['source']}\n"
        f"Price evidence: {offer.get('price_evidence', 'Internal supplier catalog')}\n"
        f"Extraction: {offer.get('extraction_method', 'internal catalog')}"
    )
    quote = Quote(
        id=f"Q-{uuid4().hex[:8].upper()}",
        case_id=case_record.id,
        company_id=case_record.company_id,
        supplier_id=supplier.id,
        product_name=offer["product_name"],
        quantity=case_record.quantity,
        unit_price=offer["unit_price"],
        total_price=offer["total_price"],
        currency=offer["currency"],
        delivery_days=offer.get("lead_time_days"),
        notes=source_notes,
        status=status,
    )
    db.add(quote)
    return quote


def _set_up_approval(db: Session, case_record: ProcurementCase, selected_quote: Quote):
    approval = Approval(
        id=f"APP-{uuid4().hex[:8].upper()}",
        case_id=case_record.id,
        company_id=case_record.company_id,
        requested_by=case_record.requested_by,
        amount=selected_quote.total_price,
        currency=selected_quote.currency,
        status="PENDING",
        comments=f"Review selected quote {selected_quote.id} before purchase.",
    )
    db.add(approval)
    case_record.status = "PENDING_APPROVAL"
    case_record.current_stage = "PENDING_APPROVAL"


def _source_case(db: Session, case_record: ProcurementCase):
    offers = find_internal_supplier_offers(
        case_record.company_id,
        case_record.product_name,
        case_record.quantity,
        case_record.budget,
        case_record.currency,
        db,
    )
    if not offers:
        try:
            offers = search_external_suppliers(
                case_record.product_name,
                case_record.budget,
                case_record.quantity,
                case_record.currency,
            )
        except SourcingError as error:
            case_record.status = "SOURCING_FAILED"
            case_record.current_stage = "SOURCING_FAILED"
            db.commit()
            raise HTTPException(status_code=502, detail=str(error)) from error

    if not offers:
        case_record.status = "NO_MATCHING_OFFERS"
        case_record.current_stage = "SOURCING_COMPLETE"
        db.commit()
        return

    selected_offer = choose_best_offer(offers)
    selected_quote = None
    for offer in offers:
        quote = _create_quote_for_offer(
            db,
            case_record,
            offer,
            "SELECTED" if offer is selected_offer else "ALTERNATIVE",
        )
        if offer is selected_offer:
            selected_quote = quote

    if selected_quote is None:
        raise RuntimeError("Sourcing returned offers but no selected offer.")

    _set_up_approval(db, case_record, selected_quote)
    db.commit()
    db.refresh(case_record)


@router.post("", response_model=CaseRead, status_code=201)
def create_case(case: CaseCreate, db: Session = Depends(get_db)):
    payload = case.model_dump()
    validation = validate_case_request(payload)
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "status": validation["status"],
                "error": validation["error"],
                "missing_fields": validation["missing_fields"],
            },
        )

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

    _source_case(db, case_record)
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


@router.post("/{case_id}/source", response_model=CaseRead)
def retry_case_sourcing(case_id: str, db: Session = Depends(get_db)):
    case = db.get(ProcurementCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in {"SOURCING_FAILED", "NO_MATCHING_OFFERS"}:
        raise HTTPException(
            status_code=409,
            detail="Only cases with failed or empty sourcing can be retried.",
        )

    _source_case(db, case)
    db.refresh(case)
    return case
