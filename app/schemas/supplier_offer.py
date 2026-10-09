from pydantic import BaseModel, Field, field_validator


class SupplierOfferUpsert(BaseModel):
    unit_price: float = Field(..., gt=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    lead_time_days: int | None = Field(default=None, ge=0)
    source: str = Field(default="INTERNAL", min_length=1, max_length=500)

    @field_validator("source", mode="before")
    @classmethod
    def trim_source(cls, value):
        return value.strip() if isinstance(value, str) else value


class SupplierOfferRead(BaseModel):
    id: str
    company_id: str
    supplier_id: str
    supplier_name: str
    product_id: str
    product_name: str
    unit_price: float | None
    currency: str
    lead_time_days: int | None
    source: str
