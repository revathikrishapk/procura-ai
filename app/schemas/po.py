from pydantic import BaseModel, Field


class PurchaseOrderCreate(BaseModel):
    case_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    supplier_id: str = Field(..., min_length=1)
    quote_id: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=2)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    delivery_days: int | None = None
    payment_terms: str | None = None
    notes: str | None = None


class PurchaseOrderRead(BaseModel):
    id: str
    case_id: str
    company_id: str
    supplier_id: str
    quote_id: str
    product_name: str
    quantity: int
    unit_price: float
    total_amount: float
    currency: str
    delivery_days: int | None = None
    payment_terms: str | None = None
    status: str
    notes: str | None = None

    class Config:
        from_attributes = True
