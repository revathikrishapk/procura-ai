from uuid import uuid4

from sqlalchemy import select

from app.models.po import PurchaseOrder
from app.models.quote import Quote


def create_purchase_order(db, state, erp_adapter):
    existing = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.case_id == state["case_id"])
    )
    if existing:
        purchase_order = existing
    else:
        quote = db.get(Quote, state["selected_quote_id"])
        if not quote:
            raise RuntimeError("The selected quote no longer exists.")
        purchase_order = PurchaseOrder(
            id=f"PO-{uuid4().hex[:8].upper()}",
            case_id=state["case_id"],
            company_id=state["company_id"],
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
            notes="Generated after explicit human approval; ERP submission is a demo adapter.",
        )
        db.add(purchase_order)
        db.flush()

    erp_result = erp_adapter.record_purchase_order({
        "id": purchase_order.id,
        "case_id": purchase_order.case_id,
        "supplier_id": purchase_order.supplier_id,
        "quote_id": purchase_order.quote_id,
        "total_amount": purchase_order.total_amount,
        "currency": purchase_order.currency,
    })
    return purchase_order, erp_result