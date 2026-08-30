from pydantic import BaseModel, Field


class ProcurementRequest(BaseModel):
    request: str = Field(
        ...,
        min_length=3,
        examples=["I need 10 laptops under $15,000"],
    )