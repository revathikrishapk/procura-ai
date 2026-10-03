from datetime import date

from pydantic import BaseModel, Field


class DeliveryCreate(BaseModel):
    po_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    supplier_id: str = Field(..., min_length=1)
    expected_days: int | None = None
    expected_delivery_date: date | None = None
    tracking_reference: str | None = None


class DeliveryRead(BaseModel):
    id: str
    po_id: str
    case_id: str
    company_id: str
    supplier_id: str
    expected_days: int | None = None
    expected_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    status: str
    tracking_reference: str | None = None

    class Config:
        from_attributes = True
