import re

from pydantic import BaseModel, Field

from app.agents.state import ProcurementState
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

try:
    from langchain_openrouter import ChatOpenRouter
except Exception:  # pragma: no cover - local fallback only
    ChatOpenRouter = None


class ExtractedProcurementRequest(BaseModel):
    item_name: str = Field(description="The product or service being requested")
    quantity: int = Field(default=1, description="Number of items requested")
    max_budget: float | None = Field(default=None, description="Maximum total budget, if mentioned")


def _fallback_parse_request(raw_request: str) -> ExtractedProcurementRequest:
    text = raw_request.strip()
    item_name = "procurement item"
    match = re.search(r"(?:for|need|buy|purchase|request|order)\s+(.*?)(?:\s+for\s+|$)", text, flags=re.IGNORECASE)
    if match:
        item_name = match.group(1).strip(" .")
        if item_name == "":
            item_name = "procurement item"
    quantity = 1
    quantity_match = re.search(r"(\d+)\s*(?:units?|pcs?|pieces?|items?|laptops?|computers?|licenses?)", text, flags=re.IGNORECASE)
    if quantity_match:
        quantity = int(quantity_match.group(1))
    budget = None
    budget_matches = re.findall(r"(?:USD|EUR|GBP|INR|AUD|CAD|JPY|\$)\s*(\d+(?:,\d{3})*(?:\.\d+)?)|\b(?:budget|under|max|limit)\s*(?:of)?\s*(\d+(?:,\d{3})*(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if budget_matches:
        for group in budget_matches:
            matched_value = next((part for part in group if part), None)
            if matched_value:
                budget = float(matched_value.replace(",", ""))
                break
    return ExtractedProcurementRequest(item_name=item_name, quantity=quantity, max_budget=budget)


async def parse_request_node(state: ProcurementState):
    raw_request = state.get("raw_request", "")
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "demo-key" and ChatOpenRouter is not None:
        model = ChatOpenRouter(model=OPENROUTER_MODEL, api_key=OPENROUTER_API_KEY, temperature=0)
        structured_model = model.with_structured_output(ExtractedProcurementRequest)
        result = await structured_model.ainvoke(
            f"""
            Extract procurement details from this request.

            Request:
            {raw_request}

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

    result = _fallback_parse_request(raw_request)
    return {
        "item_name": result.item_name,
        "quantity": result.quantity,
        "max_budget": result.max_budget,
        "status": "parsed",
    }


async def source_suppliers_node(state: ProcurementState):
    """Return deterministic demo suppliers until a supplier connector is configured."""
    return {
        "suppliers": [
            {"name": "Acme Industrial Supply", "rating": 4.7, "lead_time_days": 7},
            {"name": "Northstar Components", "rating": 4.5, "lead_time_days": 10},
            {"name": "Vertex Trade Partners", "rating": 4.2, "lead_time_days": 5},
        ],
        "status": "suppliers_sourced",
    }


async def evaluate_suppliers_node(state: ProcurementState):
    suppliers = state.get("suppliers", [])
    ranked_suppliers = sorted(
        suppliers,
        key=lambda supplier: (-float(supplier.get("rating", 0)), int(supplier.get("lead_time_days", 999))),
    )
    return {"suppliers": ranked_suppliers, "status": "suppliers_evaluated"}


async def analyze_quotations_node(state: ProcurementState):
    quantity = state.get("quantity", 1)
    budget = state.get("max_budget")
    suppliers = state.get("suppliers", [])
    quotations = []

    for index, supplier in enumerate(suppliers):
        unit_price = 100.0 + (index * 12.5)
        quotations.append({
            "supplier": supplier["name"],
            "unit_price": unit_price,
            "total": unit_price * quantity,
            "currency": "USD",
            "within_budget": budget is None or unit_price * quantity <= budget,
        })

    affordable_quotes = [quotation for quotation in quotations if quotation["within_budget"]]
    selected_quote = min(affordable_quotes or quotations, key=lambda quotation: quotation["total"])
    return {
        "quotations": quotations,
        "selected_supplier": selected_quote["supplier"],
        "recommended_total": selected_quote["total"],
        "approval_required": True,
        "status": "quotation_analyzed",
    }


async def request_approval_node(state: ProcurementState):
    return {"status": "awaiting_approval"}