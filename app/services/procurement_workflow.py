from datetime import date, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.models.delivery import Delivery
from app.models.po import PurchaseOrder
from app.models.quote import Quote


def generate_purchase_order(db: Session, approval: Approval):
    case = db.get(ProcurementCase, approval.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Approval case not found")
    if approval.status != "APPROVED" or approval.company_id != case.company_id:
        raise HTTPException(status_code=409, detail="Only an approved case may generate a purchase order.")

    quote = db.scalar(
        select(Quote).where(
            Quote.case_id == case.id,
            Quote.status == "SELECTED",
            Quote.total_price == approval.amount,
            Quote.currency == approval.currency,
        )
    )
    if not quote:
        raise HTTPException(
            status_code=409,
            detail="No selected quote matches the approved amount and currency.",
        )

    existing_order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.case_id == case.id)
    )
    if existing_order:
        return existing_order

    purchase_order = PurchaseOrder(
        id=f"PO-{uuid4().hex[:8].upper()}",
        case_id=case.id,
        company_id=case.company_id,
        supplier_id=quote.supplier_id,
        quote_id=quote.id,
        product_name=quote.product_name,
        quantity=quote.quantity,
        unit_price=quote.unit_price,
        total_amount=quote.total_price,
        currency=quote.currency,
        delivery_days=quote.delivery_days,
        payment_terms=quote.payment_terms,
        status="APPROVED",
        notes=f"Generated automatically after approval {approval.id}. {quote.notes or ''}".strip(),
    )
    db.add(purchase_order)
    db.flush()

    expected_date = (
        date.today() + timedelta(days=quote.delivery_days)
        if quote.delivery_days is not None
        else None
    )
    db.add(Delivery(
        id=f"DEL-{uuid4().hex[:8].upper()}",
        po_id=purchase_order.id,
        case_id=case.id,
        company_id=case.company_id,
        supplier_id=quote.supplier_id,
        expected_days=quote.delivery_days,
        expected_delivery_date=expected_date,
        status="PENDING",
        tracking_reference=None,
    ))
    case.status = "PO_GENERATED"
    case.current_stage = "PO_GENERATED"
    return purchase_order
