from pydantic import BaseModel, Field


class CreateOrganizationRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=255,
        examples=["Acme Corporation"],
    )


class CompanySchema(BaseModel):
    id: int
    name: str


class ProductSchema(BaseModel):
    id: int
    company_id: int
    name: str
    category: str
    unit: str


class SupplierSchema(BaseModel):
    id: int
    name: str
    contact_email: str | None = None
    country: str
    reliability_score: float
    verification_score: float


class OfferSchema(BaseModel):
    id: int
    supplier_id: int
    product_id: int
    price: float
    currency: str
    lead_time_days: int
    is_internal: bool
    source_url: str | None = None
    evidence_note: str | None = None


class ProcurementCaseSchema(BaseModel):
    id: int
    company_id: int
    product_id: int
    quantity: int
    budget: float
    currency: str
    requester_name: str
    status: str
    notes: str | None = None