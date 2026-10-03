from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    case_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    requested_by: str | None = None
    approved_by: str | None = None
    amount: float = Field(..., gt=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    comments: str | None = None


class ApprovalDecision(BaseModel):
    approved_by: str = Field(..., min_length=1, max_length=255)
    comments: str | None = None


class ApprovalRead(BaseModel):
    id: str
    case_id: str
    company_id: str
    requested_by: str | None = None
    approved_by: str | None = None
    amount: float
    currency: str
    status: str
    comments: str | None = None

    class Config:
        from_attributes = True
