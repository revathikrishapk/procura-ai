from sqlalchemy import select

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