from app.services.adapters import DemoLLMGateway, DemoRFQAdapter


def draft_supplier_rfq(offer, request, llm_gateway, rfq_adapter):
    draft = llm_gateway.draft_negotiation(offer, request)
    return rfq_adapter.create_draft(draft)


def create_demo_negotiation_agent():
    return DemoLLMGateway(), DemoRFQAdapter()
