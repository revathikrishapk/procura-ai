import os
from sqlalchemy import Column, Integer, String, Float, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class ApprovedVendor(Base):
    __tablename__ = "approved_vendors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String, nullable=False)
    item_category = Column(String, nullable=False)
    item_name = Column(String, nullable=False)
    unit_price = Column(Float, nullable=False)
    contract_terms = Column(String, default="Net-30")

DB_FILE = "internal_vendors.db"
engine = create_engine(f"sqlite:///{DB_FILE}", echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Initializes database and seeds mock enterprise vendor contracts."""
    Base.metadata.create_all(engine)
    session = SessionLocal()

    # Seed mock enterprise data if table is empty
    if session.query(ApprovedVendor).count() == 0:
        vendors = [
            ApprovedVendor(vendor_name="Enterprise TechDirect", item_category="laptop", item_name="Dell Laptop", unit_price=1200.0, contract_terms="Net-30 (10% Volume Discount)"),
            ApprovedVendor(vendor_name="Enterprise TechDirect", item_category="laptop", item_name="MacBook Pro", unit_price=1850.0, contract_terms="Net-30"),
            ApprovedVendor(vendor_name="OfficeHQ Supplies", item_category="chair", item_name="Ergonomic Chair", unit_price=180.0, contract_terms="Net-60"),
            ApprovedVendor(vendor_name="DisplaySource Global", item_category="monitor", item_name="4K Monitor", unit_price=350.0, contract_terms="Net-30"),
        ]
        session.add_all(vendors)
        session.commit()
    session.close()

def search_internal_vendors(item_keyword: str) -> list[dict]:
    """Queries internal database for approved vendors using normalized keyword matching."""
    session = SessionLocal()
    
    # Strip common plural suffixes for robust matching
    clean_keyword = item_keyword.lower().strip()
    if clean_keyword.endswith("s"):
        clean_keyword = clean_keyword[:-1]
        
    keyword = f"%{clean_keyword}%"
    
    results = session.query(ApprovedVendor).filter(
        (ApprovedVendor.item_name.ilike(keyword)) | 
        (ApprovedVendor.item_category.ilike(keyword))
    ).all()
    
    vendor_list = []
    for r in results:
        vendor_list.append({
            "vendor_name": r.vendor_name,
            "item_name": r.item_name,
            "unit_price": r.unit_price,
            "contract_terms": r.contract_terms,
            "source": "Internal Approved Vendor Database"
        })
    session.close()
    return vendor_list

def add_approved_vendor(vendor_name: str, item_category: str, item_name: str, unit_price: float, contract_terms: str = "Net-30") -> dict:
    """Inserts a new approved vendor into the SQLite database."""
    session = SessionLocal()
    
    # Check if this vendor and item combination already exists
    existing = session.query(ApprovedVendor).filter(
        ApprovedVendor.vendor_name.ilike(vendor_name),
        ApprovedVendor.item_name.ilike(item_name)
    ).first()

    if not existing:
        new_vendor = ApprovedVendor(
            vendor_name=vendor_name,
            item_category=item_category.lower(),
            item_name=item_name,
            unit_price=unit_price,
            contract_terms=contract_terms
        )
        session.add(new_vendor)
        session.commit()
        vendor_id = new_vendor.id
        session.close()
        return {"status": "created", "vendor_id": vendor_id}
    
    session.close()
    return {"status": "exists", "vendor_id": existing.id}