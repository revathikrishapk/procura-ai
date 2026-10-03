from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    company_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=2, max_length=255)
    category: str | None = None
    description: str | None = None


class ProductRead(BaseModel):
    id: str
    company_id: str
    name: str
    category: str | None = None
    description: str | None = None

    class Config:
        from_attributes = True
