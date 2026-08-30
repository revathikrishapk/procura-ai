from fastapi import FastAPI
from app.models import ProcurementRequest
from app.agents.graph import create_procurement_graph

app = FastAPI(
    title="Procura-AI",
    description="AI-powered procurement workflow API",
    version="0.1.0",
)
procurement_graph = create_procurement_graph()


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "procura-ai",
    }

@app.post("/requests")
async def create_procurement_request(
    procurement_request: ProcurementRequest,
):
    result = await procurement_graph.ainvoke(
        {
            "raw_request": procurement_request.request,
            "status": "received",
        }
    )

    return result