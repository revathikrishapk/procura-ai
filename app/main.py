from fastapi import FastAPI
from app.models import ProcurementRequest

app = FastAPI(
    title="Procura-AI",
    description="AI-powered procurement workflow API",
    version="0.1.0",
)


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
    return {
        "message": "Procurement request received",
        "request": procurement_request.request,
        "status": "pending_processing",
    }