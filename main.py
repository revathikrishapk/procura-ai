import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agents.graph import create_workflow

# Global compiled graph placeholder
procurement_graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global procurement_graph
    # Connect to SQLite checkpointer inside async lifespan
    async with AsyncSqliteSaver.from_conn_string("procurement_state.db") as memory:
        await memory.setup()
        procurement_graph = create_workflow().compile(checkpointer=memory)
        yield

app = FastAPI(lifespan=lifespan)

# Mount static files for frontend dashboard
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

# Active WebSocket connections store
active_connections: dict[str, WebSocket] = {}

class RequestInput(BaseModel):
    item_name: str
    quantity: int
    max_budget: float

class ApprovalInput(BaseModel):
    required: bool
    approved: bool
    reason: str = ""

@app.post("/api/runs")
async def start_run(payload: RequestInput):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    input_data = {
        "request": payload.dict(),
        "quotes": [],
        "approver_notes": "",
        "approved": None,
        "approval_required": False,
        "tracking_status": [],
        "current_step": "Initiated"
    }
    
    # Run graph in background task
    asyncio.create_task(run_graph_background(input_data, config, thread_id))
    return {"run_id": thread_id, "status": "started"}

async def run_graph_background(input_data, config, thread_id):
    async for event in procurement_graph.astream(input_data, config):
        for node_name, state in event.items():
            if thread_id in active_connections:
                await active_connections[thread_id].send_json(state)

@app.post("/api/runs/{run_id}/approve")
async def submit_approval(run_id: str, payload: ApprovalInput):
    config = {"configurable": {"thread_id": run_id}}
    
    # Update graph state with human decision and resume stream
    input_data = {"approved": payload.approved, "approver_notes": payload.reason}
    asyncio.create_task(run_graph_background(input_data, config, run_id))
    
    return {"status": "decision_recorded", "approved": payload.approved}

@app.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    await websocket.accept()
    active_connections[run_id] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.pop(run_id, None)