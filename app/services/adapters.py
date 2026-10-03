from __future__ import annotations

from typing import Any
from uuid import uuid4


class DemoLLMGateway:
    """Replaceable deterministic gateway used until a model provider is configured."""

    provider_name = "local-demo"

    def analyze_request(self, request: dict[str, Any]):
        return {
            "product_summary": request["product_name"].strip(),
            "requirements_summary": request.get("description") or "No additional specs provided.",
            "model_provider": self.provider_name,
        }

    def draft_negotiation(self, offer: dict[str, Any], request: dict[str, Any]):
        suggested_discount = round(float(offer["unit_price"]) * 0.05, 2)
        return {
            "supplier_name": offer["supplier_name"],
            "source": offer.get("source"),
            "subject": f"Request for quotation: {request['product_name']}",
            "body": (
                f"Please confirm availability of {request['quantity']} units of "
                f"{request['product_name']} and whether you can improve the listed "
                f"unit price of {offer['unit_price']} {offer['currency']} "
                f"(suggested target reduction: {suggested_discount} {offer['currency']}). "
                "Please confirm specifications, delivery time, warranty, and payment terms."
            ),
            "suggested_target_unit_price": max(
                0,
                round(float(offer["unit_price"]) - suggested_discount, 2),
            ),
            "status": "DRAFT_NOT_SENT",
            "provider": self.provider_name,
        }


class DemoRFQAdapter:
    provider_name = "local-demo"

    def create_draft(self, negotiation_draft: dict[str, Any]):
        return {
            **negotiation_draft,
            "rfq_id": f"RFQ-DEMO-{uuid4().hex[:8].upper()}",
            "delivery_status": "NOT_SENT",
        }


class DemoERPAdapter:
    provider_name = "local-demo"

    def record_purchase_order(self, purchase_order: dict[str, Any]):
        return {
            "provider": self.provider_name,
            "status": "RECORDED_LOCALLY",
            "external_reference": None,
            "purchase_order_id": purchase_order["id"],
        }


class DemoLogisticsAdapter:
    provider_name = "local-demo"

    def initialize_tracking(self, purchase_order: dict[str, Any]):
        return {
            "provider": self.provider_name,
            "status": "MANUAL_TRACKING",
            "tracking_reference": None,
            "purchase_order_id": purchase_order["id"],
        }
