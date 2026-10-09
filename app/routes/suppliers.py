from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.company import Company
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.schemas.supplier_offer import SupplierOfferRead, SupplierOfferUpsert
from app.schemas.supplier import SupplierCreate, SupplierRead

router = APIRouter(prefix="/suppliers")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(supplier: SupplierCreate, db: Session = Depends(get_db)):
    company = db.get(Company, supplier.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    supplier_record = Supplier(
        id=f"SUP-{uuid4().hex[:8].upper()}",
        company_id=supplier.company_id,
        name=supplier.name,
        website=supplier.website,
        email=supplier.email,
        reliability_score=supplier.reliability_score,
        verification_status=supplier.verification_status,
        discovery_source=supplier.discovery_source,
    )
    db.add(supplier_record)
    db.commit()
    db.refresh(supplier_record)
    return supplier_record


@router.get("", response_model=list[SupplierRead])
def list_suppliers(db: Session = Depends(get_db)):
    return db.scalars(select(Supplier).order_by(Supplier.name)).all()


@router.get("/company/{company_id}", response_model=list[SupplierRead])
def list_suppliers_for_company(company_id: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(Supplier)
        .where(Supplier.company_id == company_id)
        .order_by(Supplier.name)
    ).all()


@router.post("/{supplier_id}/products/{product_id}", status_code=status.HTTP_201_CREATED)
def link_supplier_to_product(supplier_id: str, product_id: str, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    product = db.get(Product, product_id)

    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.company_id == supplier.company_id,
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == product_id,
        )
    )
    if existing:
        return {"message": "Supplier already linked to this product", "supplier_id": supplier_id, "product_id": product_id}

    relation = SupplierProduct(
        id=f"SP-{uuid4().hex[:8].upper()}",
        company_id=supplier.company_id,
        supplier_id=supplier_id,
        product_id=product_id,
        last_price=None,
        currency="INR",
        lead_time_days=None,
        source="INTERNAL",
    )
    db.add(relation)
    db.commit()
    return {"message": "Supplier linked to product", "supplier_id": supplier_id, "product_id": product_id}


@router.put(
    "/{supplier_id}/products/{product_id}/offer",
    response_model=SupplierOfferRead,
)
def upsert_supplier_offer(
    supplier_id: str,
    product_id: str,
    offer: SupplierOfferUpsert,
    db: Session = Depends(get_db),
):
    supplier = db.get(Supplier, supplier_id)
    product = db.get(Product, product_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if supplier.company_id != product.company_id:
        raise HTTPException(
            status_code=409,
            detail="Supplier and product must belong to the same company.",
        )

    relation = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.company_id == supplier.company_id,
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == product_id,
        )
    )
    if relation is None:
        relation = SupplierProduct(
            id=f"SP-{uuid4().hex[:8].upper()}",
            company_id=supplier.company_id,
            supplier_id=supplier_id,
            product_id=product_id,
        )
        db.add(relation)

    relation.last_price = offer.unit_price
    relation.currency = offer.currency
    relation.lead_time_days = offer.lead_time_days
    relation.source = offer.source
    db.commit()
    db.refresh(relation)
    return {
        "id": relation.id,
        "company_id": relation.company_id,
        "supplier_id": supplier.id,
        "supplier_name": supplier.name,
        "product_id": product.id,
        "product_name": product.name,
        "unit_price": relation.last_price,
        "currency": relation.currency,
        "lead_time_days": relation.lead_time_days,
        "source": relation.source,
    }


@router.get(
    "/offers/company/{company_id}",
    response_model=list[SupplierOfferRead],
)
def list_offers_for_company(company_id: str, db: Session = Depends(get_db)):
    return get_supplier_offers(db, company_id)


def get_supplier_offers(db: Session, company_id: str | None = None):
    statement = (
        select(SupplierProduct, Supplier, Product)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .join(Product, Product.id == SupplierProduct.product_id)
    )
    if company_id is not None:
        statement = statement.where(SupplierProduct.company_id == company_id)
    rows = db.execute(
        statement
        .order_by(Product.name, Supplier.name)
    ).all()
    return [
        {
            "id": relation.id,
            "company_id": relation.company_id,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "product_id": product.id,
            "product_name": product.name,
            "unit_price": relation.last_price,
            "currency": relation.currency,
            "lead_time_days": relation.lead_time_days,
            "source": relation.source,
        }
        for relation, supplier, product in rows
    ]


@router.get("/offers", response_model=list[SupplierOfferRead])
def list_supplier_offers(db: Session = Depends(get_db)):
    return get_supplier_offers(db)


@router.get("/product/{product_id}", response_model=list[SupplierRead])
def list_suppliers_for_product(product_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Supplier)
        .join(SupplierProduct, Supplier.id == SupplierProduct.supplier_id)
        .where(SupplierProduct.product_id == product_id)
        .order_by(Supplier.name)
    ).scalars().all()
    return rows
