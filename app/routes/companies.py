from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyRead

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Company).where(Company.name == company.name))
    if existing:
        raise HTTPException(status_code=400, detail="Company already exists")

    company_record = Company(
        id=f"COMP-{uuid4().hex[:8].upper()}",
        name=company.name,
    )
    db.add(company_record)
    db.commit()
    db.refresh(company_record)
    return company_record


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)):
    return db.scalars(select(Company).order_by(Company.name)).all()
