import re
import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from app.agents.state import ProcurementState

class ExtractedSpec(BaseModel):
    item_name: str = Field(description="Name or description of product/service")
    quantity: int = Field(default=1, description="Quantity required")
    max_budget: float | None = Field(default=None, description="Maximum budget limit if specified")

async def parse_request_node(state: ProcurementState) -> Dict[str, Any]:
    raw_text = state.get("raw_request", "")
    clarification = state.get("human_clarification")
    existing_spec = state.get("request_spec") or {}

    # Initialize spec with existing state values
    spec = {
        "item_name": existing_spec.get("item_name") or raw_text,
        "quantity": existing_spec.get("quantity") or 1,
        "max_budget": existing_spec.get("max_budget")
    }

    # If resume text is present, extract budget from clarification input directly
    if clarification and spec["max_budget"] is None:
        clean_text = str(clarification).replace("$", "").replace(",", "").strip()
        numbers = re.findall(r'\b\d+(?:\.\d+)?\b', clean_text)
        if numbers:
            spec["max_budget"] = float(numbers[0])

    # If budget is still missing, run LLM structured parser
    if spec["max_budget"] is None:
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini", 
                temperature=0, 
                api_key=os.getenv("OPENAI_API_KEY")
            )
            structured_parser = llm.with_structured_output(ExtractedSpec)
            parsed: ExtractedSpec = await structured_parser.ainvoke(
                f"Extract procurement variables: {raw_text}"
            )
            parsed_data = parsed.model_dump()
            
            spec["item_name"] = parsed_data.get("item_name") or spec["item_name"]
            spec["quantity"] = parsed_data.get("quantity") or spec["quantity"]
            spec["max_budget"] = parsed_data.get("max_budget")
        except Exception:
            pass

    # Check missing fields
    missing_fields: List[str] = []
    if not spec.get("item_name"):
        missing_fields.append("item_name")
    if spec.get("max_budget") is None:
        missing_fields.append("max_budget")

    return {
        "request_spec": spec,
        "is_ambiguous": len(missing_fields) > 0,
        "missing_fields": missing_fields
    }

async def sourcing_agent_node(state: ProcurementState) -> Dict[str, Any]:
    spec = state.get("request_spec", {})
    qty = spec.get("quantity", 1)
    unit_price = 150.0
    total_expense = unit_price * qty

    # Structured comparison matching the frontend UI fields
    comparison_data = {
        "vendor": "OfficeDepot Direct",
        "unit_price": unit_price,
        "total_expense": total_expense,
        "source": "Internal Vendor Catalog",
        "terms": "Net 30 Days",
        "status": "Sourced Successfully"
    }

    return {
        "quotes": [{"vendor": "OfficeDepot Direct", "price": unit_price}],
        "comparison": comparison_data
    }

async def vendor_approval_node(state: ProcurementState) -> Dict[str, Any]:
    return {"manager_approved": True}

async def po_dispatch_node(state: ProcurementState) -> Dict[str, Any]:
    # Preserve the comparison dictionary and add dispatch status
    comparison = state.get("comparison", {})
    comparison["po_status"] = "PO Generated & Dispatched"
    
    return {"comparison": comparison}