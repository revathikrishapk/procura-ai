from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.case import ProcurementCase
from app.models.quote import Quote
from app.models.supplier import Supplier
from app.schemas.quote import QuoteCreate, QuoteRead

router = APIRouter(prefix="/quotes")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=QuoteRead, status_code=201)
def create_quote(quote: QuoteCreate, db: Session = Depends(get_db)):
    case = db.get(ProcurementCase, quote.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    supplier = db.get(Supplier, quote.supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    total = quote.unit_price * quote.quantity
    quote_record = Quote(
        id=f"Q-{uuid4().hex[:8].upper()}",
        case_id=quote.case_id,
        company_id=quote.company_id,
        supplier_id=quote.supplier_id,
        product_name=quote.product_name,
        quantity=quote.quantity,
        unit_price=quote.unit_price,
        total_price=total,
        currency=quote.currency,
        delivery_days=quote.delivery_days,
        payment_terms=quote.payment_terms,
        validity_days=quote.validity_days,
        notes=quote.notes,
        status="RECEIVED",
    )
    db.add(quote_record)
    db.commit()
    db.refresh(quote_record)
    return quote_record


@router.get("", response_model=list[QuoteRead])
def list_quotes(db: Session = Depends(get_db)):
    return db.scalars(select(Quote).order_by(Quote.id)).all()


@router.get("/case/{case_id}", response_model=list[QuoteRead])
def list_quotes_for_case(case_id: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(Quote)
        .where(Quote.case_id == case_id)
        .order_by(Quote.total_price)
    ).all()
