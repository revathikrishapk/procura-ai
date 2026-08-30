from dotenv import load_dotenv
load_dotenv()  # MUST BE AT LINE 1 (loads before local modules import)

import uuid
import os
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Local imports (loaded after env vars are populated)
from app.agents.graph import create_workflow
from app.agents.state import ProcurementState
from app.db import init_db

compiled_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global compiled_app
    init_db()
    
    async with AsyncSqliteSaver.from_conn_string("procurement_state.db") as checkpointer:
        compiled_app = create_workflow().compile(checkpointer=checkpointer)
        yield

app = FastAPI(title="Procura AI - Internal DB Sourcing", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InitialRequestPayload(BaseModel):
    request: str

class ClarificationPayload(BaseModel):
    additional_text: str

class ApprovalPayload(BaseModel):
    approved: bool

@app.get("/")
async def root():
    return {"status": "online", "system": "Procura AI Engine", "docs": "/docs"}

@app.get("/api/v1/procurement/download-po/{po_number}")
async def download_po(po_number: str):
    """Serves the generated Purchase Order PDF for download."""
    file_path = os.path.join("generated_pos", f"{po_number}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Purchase Order PDF not found.")
    
    return FileResponse(
        path=file_path,
        filename=f"{po_number}.pdf",
        media_type="application/pdf"
    )

@app.post("/api/v1/procurement/run")
async def start_procurement_run(payload: InitialRequestPayload):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: ProcurementState = {
        "raw_request": payload.request,
        "request_spec": {},
        "quotes": [],
        "comparison": {},
        "is_ambiguous": False,
        "missing_fields": [],
        "human_clarification": None,
        "error": None
    }

    final_state = await compiled_app.ainvoke(initial_state, config=config)

    return {
        "thread_id": thread_id,
        "status": "AWAITING_HUMAN_INPUT" if final_state.get("is_ambiguous") else "COMPLETED",
        "missing_fields": final_state.get("missing_fields"),
        "extracted_spec": final_state.get("request_spec"),
        "comparison_result": final_state.get("comparison") if not final_state.get("is_ambiguous") else None
    }

@app.post("/api/v1/procurement/run/{thread_id}/resume")
async def resume_procurement_run(thread_id: str, payload: ClarificationPayload):
    config = {"configurable": {"thread_id": thread_id}}

    current_state = await compiled_app.aget_state(config)
    if not current_state.values:
        raise HTTPException(status_code=404, detail="Thread ID not found.")

    # Parse budget number directly from human clarification text
    raw_input = payload.additional_text.replace("$", "").replace(",", "").strip()
    extracted_numbers = re.findall(r'\b\d+(?:\.\d+)?\b', raw_input)
    
    existing_spec = current_state.values.get("request_spec", {})
    if extracted_numbers:
        existing_spec["max_budget"] = float(extracted_numbers[0])

    # Forcefully override state variables so graph moves to sourcing
    await compiled_app.aupdate_state(
        config, 
        {
            "human_clarification": payload.additional_text,
            "request_spec": existing_spec,
            "is_ambiguous": False,
            "missing_fields": []
        }
    )

    final_state = await compiled_app.ainvoke(None, config=config)

    return {
        "thread_id": thread_id,
        "status": "AWAITING_HUMAN_INPUT" if final_state.get("is_ambiguous") else "COMPLETED",
        "missing_fields": final_state.get("missing_fields"),
        "extracted_spec": final_state.get("request_spec"),
        "comparison_result": final_state.get("comparison")
    }

@app.post("/api/v1/procurement/run/{thread_id}/approve-vendor")
async def approve_vendor_run(thread_id: str, payload: ApprovalPayload):
    """Resumes execution after a manager approves or rejects an external vendor."""
    config = {"configurable": {"thread_id": thread_id}}

    current_state = await compiled_app.aget_state(config)
    if not current_state.values:
        raise HTTPException(status_code=404, detail="Thread ID not found.")

    if not payload.approved:
        return {
            "thread_id": thread_id,
            "status": "REJECTED_BY_MANAGER",
            "message": "External vendor rejected by manager. PO generation cancelled."
        }

    await compiled_app.aupdate_state(
        config, 
        {"manager_approved": True, "requires_manager_approval": False}
    )
    
    final_state = await compiled_app.ainvoke(None, config=config)

    return {
        "thread_id": thread_id,
        "status": "COMPLETED",
        "comparison_result": final_state.get("comparison")
    }