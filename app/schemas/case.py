from pydantic import BaseModel, Field, field_validator


class CaseCreate(BaseModel):
    company_id: str = Field(..., min_length=1)
    requested_by: str | None = None
    product_name: str = Field(..., min_length=2, max_length=255)
    quantity: int = Field(..., gt=0)
    description: str | None = None
    budget: float = Field(..., gt=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")

    @field_validator("company_id", "product_name", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class CaseRead(BaseModel):
    id: str
    company_id: str
    requested_by: str | None = None
    product_name: str
    quantity: int
    description: str | None = None
    budget: float | None = None
    currency: str
    status: str
    current_stage: str

    class Config:
        from_attributes = True
