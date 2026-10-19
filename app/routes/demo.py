import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import DATABASE_URL, SessionLocal
from app.models.company import Company
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_COMPANY_ID = "DEMO-COMPANY"
DEMO_PRODUCT_ID = "DEMO-PRODUCT"
DEMO_SUPPLIER_ID = "DEMO-SUPPLIER"
DEMO_OFFER_ID = "DEMO-OFFER"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    if (
        not DATABASE_URL.startswith("sqlite")
        or os.getenv("APP_ENV", "development").lower() in {"prod", "production"}
    ):
        raise HTTPException(
            status_code=403,
            detail="Demo data can only be seeded in a local SQLite environment.",
        )

    company = db.get(Company, DEMO_COMPANY_ID)
    company_by_name = db.scalar(
        select(Company).where(Company.name == "Procura Demo Company")
    )
    if company_by_name is not None and company_by_name.id != DEMO_COMPANY_ID:
        raise HTTPException(
            status_code=409,
            detail="A company named 'Procura Demo Company' already exists.",
        )
    if company is None:
        company = Company(id=DEMO_COMPANY_ID, name="Procura Demo Company")
        db.add(company)
    else:
        company.name = "Procura Demo Company"

    product = db.get(Product, DEMO_PRODUCT_ID)
    if product is None:
        product = Product(
            id=DEMO_PRODUCT_ID,
            company_id=DEMO_COMPANY_ID,
            name="Demo GPU",
            category="GPU",
            description="Seeded catalog item for a local workflow demo.",
        )
        db.add(product)
    elif product.company_id != DEMO_COMPANY_ID:
        raise HTTPException(
            status_code=409,
            detail=f"Reserved demo product ID {DEMO_PRODUCT_ID} is already in use.",
        )
    else:
        product.name = "Demo GPU"
        product.category = "GPU"
        product.description = "Seeded catalog item for a local workflow demo."

    supplier = db.get(Supplier, DEMO_SUPPLIER_ID)
    if supplier is None:
        supplier = Supplier(
            id=DEMO_SUPPLIER_ID,
            company_id=DEMO_COMPANY_ID,
            name="Demo Supplier",
            reliability_score=0.9,
            verification_status="VERIFIED",
            discovery_source="INTERNAL",
        )
        db.add(supplier)
    elif supplier.company_id != DEMO_COMPANY_ID:
        raise HTTPException(
            status_code=409,
            detail=f"Reserved demo supplier ID {DEMO_SUPPLIER_ID} is already in use.",
        )
    else:
        supplier.name = "Demo Supplier"
        supplier.reliability_score = 0.9
        supplier.verification_status = "VERIFIED"
        supplier.discovery_source = "INTERNAL"

    offer = db.get(SupplierProduct, DEMO_OFFER_ID)
    if offer is None:
        offer = db.scalar(
            select(SupplierProduct).where(
                SupplierProduct.company_id == DEMO_COMPANY_ID,
                SupplierProduct.supplier_id == DEMO_SUPPLIER_ID,
                SupplierProduct.product_id == DEMO_PRODUCT_ID,
            )
        )
    if offer is None:
        offer = SupplierProduct(
            id=DEMO_OFFER_ID,
            company_id=DEMO_COMPANY_ID,
            supplier_id=DEMO_SUPPLIER_ID,
            product_id=DEMO_PRODUCT_ID,
            last_price=120000,
            currency="INR",
            lead_time_days=7,
            source="DEMO",
        )
        db.add(offer)
    else:
        if (
            offer.company_id != DEMO_COMPANY_ID
            or offer.supplier_id != DEMO_SUPPLIER_ID
            or offer.product_id != DEMO_PRODUCT_ID
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Reserved demo offer ID {DEMO_OFFER_ID} is already in use.",
            )
        offer.last_price = 120000
        offer.currency = "INR"
        offer.lead_time_days = 7
        offer.source = "DEMO"

    db.commit()
    return {
        "company_id": company.id,
        "product_id": product.id,
        "supplier_id": supplier.id,
        "offer_id": offer.id,
        "message": "Demo catalog is ready.",
    }
