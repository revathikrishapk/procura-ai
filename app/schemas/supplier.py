from pydantic import BaseModel, Field


class SupplierCreate(BaseModel):
    company_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=2, max_length=255)
    website: str | None = None
    email: str | None = None
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_status: str = Field(
        default="UNVERIFIED",
        pattern="^(VERIFIED|UNVERIFIED)$",
    )
    discovery_source: str = "INTERNAL"


class SupplierRead(BaseModel):
    id: str
    company_id: str
    name: str
    website: str | None = None
    email: str | None = None
    reliability_score: float
    verification_status: str
    discovery_source: str

    class Config:
        from_attributes = True
