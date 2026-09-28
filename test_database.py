from app.db import SessionLocal
from app.models.company import Company
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct


db = SessionLocal()

company = Company(
    id="COMP-001",
    name="Demo Corporation"
)

product = Product(
    id="PROD-001",
    company_id="COMP-001",
    name="NVIDIA H100",
    category="GPU",
    description="Enterprise AI accelerator"
)

supplier = Supplier(
    id="SUP-001",
    company_id="COMP-001",
    name="Example Supplier",
    website="https://example.com",
    verification_status="VERIFIED",
    discovery_source="INTERNAL"
)

supplier_product = SupplierProduct(
    id="SP-001",
    company_id="COMP-001",
    supplier_id="SUP-001",
    product_id="PROD-001",
    last_price=2500000,
    currency="INR",
    lead_time_days=14,
    source="INTERNAL"
)

db.add(company)
db.add(product)
db.add(supplier)
db.add(supplier_product)

db.commit()

print("Test data inserted successfully.")

db.close()