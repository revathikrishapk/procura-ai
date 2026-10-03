from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.models.case import ProcurementCase
from app.models.delivery import Delivery
from app.models.po import PurchaseOrder


def start_delivery_tracking(db, state, logistics_adapter):
    purchase_order = db.get(PurchaseOrder, state["po_id"])
    if not purchase_order:
        raise RuntimeError("Purchase order disappeared before delivery setup.")

    delivery_record = db.scalar(
        select(Delivery).where(Delivery.po_id == purchase_order.id)
    )
    if not delivery_record:
        expected_date = (
            date.today() + timedelta(days=purchase_order.delivery_days)
            if purchase_order.delivery_days is not None
            else None
        )
        delivery_record = Delivery(
            id=f"DEL-{uuid4().hex[:8].upper()}",
            po_id=purchase_order.id,
            case_id=state["case_id"],
            company_id=state["company_id"],
            supplier_id=purchase_order.supplier_id,
            expected_days=purchase_order.delivery_days,
            expected_delivery_date=expected_date,
            status="PENDING",
        )
        db.add(delivery_record)
        db.flush()

    tracking = logistics_adapter.initialize_tracking({
        "id": purchase_order.id,
        "delivery_id": delivery_record.id,
        "supplier_id": purchase_order.supplier_id,
    })
    case = db.get(ProcurementCase, state["case_id"])
    if case:
        case.status = "DELIVERY_IN_PROGRESS"
        case.current_stage = "DELIVERY_TRACKING"
    return delivery_record, tracking