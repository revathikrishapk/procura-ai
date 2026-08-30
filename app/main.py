from fastapi import FastAPI

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