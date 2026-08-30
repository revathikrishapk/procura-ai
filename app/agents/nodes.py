from pydantic import BaseModel, Field
from langchain_openrouter import ChatOpenRouter

from app.agents.state import ProcurementState
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL


class ExtractedProcurementRequest(BaseModel):
    item_name: str = Field(
        description="The product or service being requested"
    )
    quantity: int = Field(
        default=1,
        description="Number of items requested"
    )
    max_budget: float | None = Field(
        default=None,
        description="Maximum total budget, if mentioned"
    )


async def parse_request_node(
    state: ProcurementState,
):
    model = ChatOpenRouter(
        model=OPENROUTER_MODEL,
        api_key=OPENROUTER_API_KEY,
        temperature=0,
    )

    structured_model = model.with_structured_output(
        ExtractedProcurementRequest
    )

    result = await structured_model.ainvoke(
        f"""
        Extract procurement details from this request.

        Request:
        {state["raw_request"]}

        Rules:
        - Extract the item or service.
        - Extract quantity.
        - Extract the maximum TOTAL budget if mentioned.
        - If no budget is mentioned, return null.
        - Do not invent values.
        """
    )

    return {
        "item_name": result.item_name,
        "quantity": result.quantity,
        "max_budget": result.max_budget,
        "status": "parsed",
    }