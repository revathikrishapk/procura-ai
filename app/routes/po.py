from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.models.po import PurchaseOrder
from app.models.quote import Quote
from app.schemas.po import PurchaseOrderCreate, PurchaseOrderRead
from app.services.procurement_workflow import generate_purchase_order

router = APIRouter(prefix="/purchase-orders")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=PurchaseOrderRead, status_code=201)
def create_purchase_order(purchase_order: PurchaseOrderCreate, db: Session = Depends(get_db)):
    case = db.get(ProcurementCase, purchase_order.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    quote = db.get(Quote, purchase_order.quote_id)
    if not quote or quote.case_id != case.id or quote.status != "SELECTED":
        raise HTTPException(status_code=404, detail="Quote not found")

    approval = db.scalar(
        select(Approval).where(
            Approval.case_id == case.id,
            Approval.status == "APPROVED",
            Approval.amount == quote.total_price,
            Approval.currency == quote.currency,
        )
    )
    if not approval:
        raise HTTPException(status_code=409, detail="Purchase orders require an approved quote.")

    if (
        purchase_order.company_id != case.company_id
        or purchase_order.supplier_id != quote.supplier_id
        or purchase_order.product_name != quote.product_name
        or purchase_order.quantity != quote.quantity
        or purchase_order.unit_price != quote.unit_price
        or purchase_order.currency != quote.currency
    ):
        raise HTTPException(status_code=409, detail="Purchase order must match the approved quote.")

    po_record = generate_purchase_order(db, approval)
    db.commit()
    db.refresh(po_record)
    return po_record


@router.get("", response_model=list[PurchaseOrderRead])
def list_purchase_orders(db: Session = Depends(get_db)):
    return db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id)).all()


@router.get("/{po_id}", response_model=PurchaseOrderRead)
def get_purchase_order(po_id: str, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


@router.patch("/{po_id}/status", response_model=PurchaseOrderRead)
def update_purchase_order_status(
    po_id: str,
    new_status: str,
    db: Session = Depends(get_db),
):
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if new_status != "ISSUED":
        raise HTTPException(status_code=400, detail="Status must be ISSUED")
    if po.status not in {"APPROVED", "ISSUED"}:
        raise HTTPException(status_code=409, detail="Only approved purchase orders can be updated")
    po.status = new_status
    case = db.get(ProcurementCase, po.case_id)
    if case:
        case.status = "ORDER_PLACED"
        case.current_stage = "ORDER_PLACED"
    db.commit()
    db.refresh(po)
    return po
