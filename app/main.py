from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import CreateOrganizationRequest
from app.db_models import OrganizationDB


from app.database import get_db

from contextlib import asynccontextmanager

from app.database import Base, engine
from app.db_models import ProcurementRequestDB

from app.agents.graph import create_procurement_graph
from app.models import ProcurementRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()


app = FastAPI(
    title="Procura-AI",
    description="AI-powered procurement workflow API",
    version="0.1.0",
    lifespan=lifespan,
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
    db: AsyncSession = Depends(get_db),
):
    result = await procurement_graph.ainvoke(
        {
            "raw_request": procurement_request.request,
            "status": "received",
        }
    )

    new_request = ProcurementRequestDB(
        raw_request=procurement_request.request,
        item_name=result.get("item_name"),
        quantity=result.get("quantity"),
        max_budget=result.get("max_budget"),
        status=result.get("status", "parsed"),
    )

    db.add(new_request)

    await db.commit()
    await db.refresh(new_request)

    return {
        "id": new_request.id,
        "item_name": new_request.item_name,
        "quantity": new_request.quantity,
        "max_budget": new_request.max_budget,
        "status": new_request.status,
        "created_at": new_request.created_at,
    }

@app.get("/requests")
async def get_procurement_requests(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProcurementRequestDB)
        .order_by(ProcurementRequestDB.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    requests = result.scalars().all()

    return {
        "count": len(requests),
        "requests": [
            {
                "id": request.id,
                "raw_request": request.raw_request,
                "item_name": request.item_name,
                "quantity": request.quantity,
                "max_budget": request.max_budget,
                "status": request.status,
                "created_at": request.created_at,
            }
            for request in requests
        ],
    }


@app.get("/requests/{request_id}")
async def get_procurement_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProcurementRequestDB).where(
            ProcurementRequestDB.id == request_id
        )
    )

    procurement_request = result.scalar_one_or_none()

    if not procurement_request:
        raise HTTPException(
            status_code=404,
            detail="Procurement request not found",
        )

    return {
        "id": procurement_request.id,
        "raw_request": procurement_request.raw_request,
        "item_name": procurement_request.item_name,
        "quantity": procurement_request.quantity,
        "max_budget": procurement_request.max_budget,
        "status": procurement_request.status,
        "created_at": procurement_request.created_at,
    }

@app.post("/organizations")
async def create_organization(
    organization: CreateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
):
    new_organization = OrganizationDB(
        name=organization.name,
    )

    db.add(new_organization)

    await db.commit()
    await db.refresh(new_organization)

    return {
        "id": str(new_organization.id),
        "name": new_organization.name,
        "created_at": new_organization.created_at,
    }