from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.case import ProcurementCase
from app.models.delivery import Delivery
from app.models.po import PurchaseOrder
from app.schemas.delivery import DeliveryCreate, DeliveryRead

router = APIRouter(prefix="/deliveries")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=DeliveryRead, status_code=201)
def create_delivery(delivery: DeliveryCreate, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, delivery.po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if po.status not in {"APPROVED", "ISSUED"}:
        raise HTTPException(
            status_code=409,
            detail="Delivery tracking can only be opened for an approved purchase order.",
        )
    if (
        delivery.case_id != po.case_id
        or delivery.company_id != po.company_id
        or delivery.supplier_id != po.supplier_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Delivery details must match the purchase order.",
        )

    delivery_record = Delivery(
        id=f"DEL-{uuid4().hex[:8].upper()}",
        po_id=delivery.po_id,
        case_id=delivery.case_id,
        company_id=delivery.company_id,
        supplier_id=delivery.supplier_id,
        expected_days=delivery.expected_days,
        expected_delivery_date=delivery.expected_delivery_date,
        actual_delivery_date=None,
        status="PENDING",
        tracking_reference=delivery.tracking_reference,
    )
    db.add(delivery_record)
    db.commit()
    db.refresh(delivery_record)
    return delivery_record


@router.get("", response_model=list[DeliveryRead])
def list_deliveries(db: Session = Depends(get_db)):
    return db.scalars(select(Delivery).order_by(Delivery.id)).all()


@router.patch("/{delivery_id}/status", response_model=DeliveryRead)
def update_delivery_status(delivery_id: str, new_status: str, db: Session = Depends(get_db)):
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if new_status not in {"PENDING", "IN_TRANSIT", "DELIVERED", "DELAYED"}:
        raise HTTPException(
            status_code=400,
            detail="Status must be PENDING, IN_TRANSIT, DELIVERED, or DELAYED",
        )
    delivery.status = new_status
    if new_status == "DELIVERED":
        delivery.actual_delivery_date = date.today()
        case = db.get(ProcurementCase, delivery.case_id)
        if case:
            case.status = "CLOSED"
            case.current_stage = "CLOSED"
    db.commit()
    db.refresh(delivery)
    return delivery
