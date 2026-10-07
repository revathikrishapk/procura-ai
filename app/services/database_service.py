from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct


def find_product(company_id: str, product_name: str):
    db = SessionLocal()

    try:
        statement = select(Product).where(
            Product.company_id == company_id,
            Product.name.ilike(f"%{product_name}%")
        )

        return db.scalars(statement).first()

    finally:
        db.close()


def find_suppliers_for_product(
    company_id: str,
    product_id: str
):
    db = SessionLocal()

    try:
        statement = (
            select(Supplier, SupplierProduct)
            .join(
                SupplierProduct,
                Supplier.id == SupplierProduct.supplier_id
            )
            .where(
                Supplier.company_id == company_id,
                SupplierProduct.product_id == product_id
            )
        )

        return db.execute(statement).all()

    finally:
        db.close()


def find_internal_supplier_offers(
    company_id: str,
    product_name: str,
    quantity: int,
    budget: float | None = None,
    currency: str = "INR",
    db: Session | None = None,
):
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        product = db.scalars(
            select(Product).where(
                Product.company_id == company_id,
                Product.name.ilike(f"%{product_name}%"),
            )
        ).first()
        if not product:
            return []

        supplier_rows = db.execute(
            select(Supplier, SupplierProduct)
            .join(SupplierProduct, Supplier.id == SupplierProduct.supplier_id)
            .where(
                Supplier.company_id == company_id,
                SupplierProduct.company_id == company_id,
                SupplierProduct.product_id == product.id,
            )
        ).all()

        offers = []
        for supplier, supplier_product in supplier_rows:
            if supplier_product.last_price is None:
                continue
            if (supplier_product.currency or "INR").upper() != currency.upper():
                continue

            total_price = supplier_product.last_price * quantity
            if budget is not None and total_price > budget:
                continue

            offers.append({
                "supplier_id": supplier.id,
                "supplier_name": supplier.name,
                "reliability_score": float(supplier.reliability_score or 0),
                "verification_status": supplier.verification_status,
                "product_id": product.id,
                "product_name": product.name,
                "unit_price": float(supplier_product.last_price),
                "total_price": float(total_price),
                "currency": supplier_product.currency or "INR",
                "lead_time_days": supplier_product.lead_time_days,
                "source": supplier_product.source,
                "source_type": "internal",
            })

        return sorted(
            offers,
            key=lambda offer: (
                offer["total_price"],
                offer["lead_time_days"] or 9999,
            ),
        )
    finally:
        if owns_session:
            db.close()