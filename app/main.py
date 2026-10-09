from contextlib import asynccontextmanager
from contextlib import ExitStack
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver

from app.db import init_db
from app.routes import approvals, cases, companies, delivery, po, products, quotes, suppliers
from app.services.langgraph_workflow import create_procurement_graph

@asynccontextmanager
async def lifespan(app):
    init_db()
    with ExitStack() as stack:
        checkpointer = stack.enter_context(
            SqliteSaver.from_conn_string(
                os.getenv(
                    "LANGGRAPH_CHECKPOINT_PATH",
                    "procura_checkpoints.sqlite",
                )
            )
        )
        checkpointer.setup()
        app.state.procurement_graph = create_procurement_graph(checkpointer)
        yield


app = FastAPI(
    title="Procura AI MVP",
    version="0.1.0",
    description="Procurement workflow MVP for intake, sourcing, approval, PO, and delivery tracking.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(products.router)
app.include_router(suppliers.router)
app.include_router(cases.router)
app.include_router(quotes.router)
app.include_router(approvals.router)
app.include_router(po.router)
app.include_router(delivery.router)


@app.get("/")
def root():
    return {
        "message": "Procura AI MVP is running",
        "status": "ok",
    }
