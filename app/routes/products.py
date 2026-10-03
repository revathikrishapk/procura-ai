from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.company import Company
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductRead

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    company = db.get(Company, product.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    product_record = Product(
        id=f"PROD-{uuid4().hex[:8].upper()}",
        company_id=product.company_id,
        name=product.name,
        category=product.category,
        description=product.description,
    )
    db.add(product_record)
    db.commit()
    db.refresh(product_record)
    return product_record


@router.get("/products", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.name)).all()


@router.get("/products/company/{company_id}", response_model=list[ProductRead])
def list_products_for_company(company_id: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(Product)
        .where(Product.company_id == company_id)
        .order_by(Product.name)
    ).all()
