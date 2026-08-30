from app.agents.state import ProcurementState


async def parse_request_node(state: ProcurementState):
    return {
        "status": "parsed",
    }