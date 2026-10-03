from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)


class CompanyRead(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True
