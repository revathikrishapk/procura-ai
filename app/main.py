from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import create_procurement_graph
from app.config import APP_ENV
from app.database import Base, engine, get_db
from app.db_models import (
    ApprovalDecisionDB,
    CompanyDB,
    DeliveryUpdateDB,
    OrganizationDB,
    ProcurementCaseDB,
    ProcurementRequestDB,
    ProductDB,
    PurchaseOrderDB,
    SupplierDB,
    SupplierOfferDB,
)
from app.models import (
    ApprovalAction,
    CompanyCreate,
    DeliveryUpdate,
    ProcurementCaseCreate,
    ProcurementRequest,
    ProductCreate,
    SupplierCreate,
    SupplierOfferCreate,
)
from app.schemas import CreateOrganizationRequest


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


def _normalize_currency(value: str) -> str:
    return (value or "USD").upper()


def _is_valid_currency(value: str) -> bool:
    return value.upper() in {"USD", "EUR", "GBP", "AED", "INR", "JPY", "CAD", "AUD"}


async def _get_case_or_404(case_id: int, db: AsyncSession) -> ProcurementCaseDB:
    result = await db.execute(select(ProcurementCaseDB).where(ProcurementCaseDB.id == case_id))
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Procurement case not found")
    return case


async def _get_offer_candidates(case: ProcurementCaseDB, db: AsyncSession):
    result = await db.execute(
        select(SupplierOfferDB)
        .where(SupplierOfferDB.product_id == case.product_id)
        .order_by(SupplierOfferDB.price.asc())
    )
    return result.scalars().all()


async def _generate_workflow_summary(case: ProcurementCaseDB, db: AsyncSession) -> dict[str, Any]:
    offers = await _get_offer_candidates(case, db)
    approval_result = await db.execute(select(ApprovalDecisionDB).where(ApprovalDecisionDB.case_id == case.id).limit(1))
    approval = approval_result.scalar_one_or_none()
    approval_record = None
    if approval:
        approval_record = {
            "id": approval.id,
            "approver_name": approval.approver_name,
            "requester_name": approval.requester_name,
            "decision": approval.decision,
            "reason": approval.reason,
            "created_at": approval.created_at,
        }
    po_result = await db.execute(select(PurchaseOrderDB).where(PurchaseOrderDB.case_id == case.id).limit(1))
    po = po_result.scalar_one_or_none()
    po_record = None
    if po:
        po_record = {
            "id": po.id,
            "supplier_id": po.supplier_id,
            "product_id": po.product_id,
            "quantity": po.quantity,
            "unit_price": po.unit_price,
            "currency": po.currency,
            "total_price": po.total_price,
            "status": po.status,
            "created_at": po.created_at,
        }
    latest_delivery = None
    if po:
        delivery_result = await db.execute(
            select(DeliveryUpdateDB)
            .where(DeliveryUpdateDB.po_id == po.id)
            .order_by(DeliveryUpdateDB.created_at.desc())
            .limit(1)
        )
        delivery_row = delivery_result.scalar_one_or_none()
        if delivery_row:
            latest_delivery = {
                "id": delivery_row.id,
                "status": delivery_row.status,
                "updated_by": delivery_row.updated_by,
                "notes": delivery_row.notes,
                "created_at": delivery_row.created_at,
            }

    return {
        "case_id": case.id,
        "status": case.status,
        "current_stage": case.current_stage,
        "source_summary": {
            "eligible_offers": [
                {
                    "id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "price": offer.price,
                    "currency": offer.currency,
                    "lead_time_days": offer.lead_time_days,
                    "is_internal": offer.is_internal,
                }
                for offer in offers
            ]
        },
        "evaluation_summary": {
            "currency": case.currency,
            "quantity": case.quantity,
            "budget": case.budget,
            "offers_considered": len(offers),
        },
        "approval": approval_record,
        "purchase_order": po_record,
        "delivery": latest_delivery,
    }


@app.get("/")
async def home_page():
    index_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Procura AI demo backend is running."}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "procura-ai", "environment": APP_ENV}


@app.post("/requests")
async def create_procurement_request(
    procurement_request: ProcurementRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await procurement_graph.ainvoke({"raw_request": procurement_request.request, "status": "received"})
    new_request = ProcurementRequestDB(
        raw_request=procurement_request.request,
        item_name=result.get("item_name"),
        quantity=result.get("quantity"),
        max_budget=result.get("max_budget"),
        status=result.get("status", "parsed"),
        workflow_state=dict(result),
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
        "workflow_state": new_request.workflow_state,
        "created_at": new_request.created_at,
    }


@app.get("/requests")
async def get_procurement_requests(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProcurementRequestDB).order_by(ProcurementRequestDB.created_at.desc()).offset(skip).limit(limit)
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
                "workflow_state": request.workflow_state,
                "created_at": request.created_at,
            }
            for request in requests
        ],
    }


@app.get("/requests/{request_id}")
async def get_procurement_request(request_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProcurementRequestDB).where(ProcurementRequestDB.id == request_id))
    procurement_request = result.scalar_one_or_none()
    if not procurement_request:
        raise HTTPException(status_code=404, detail="Procurement request not found")
    return {
        "id": procurement_request.id,
        "raw_request": procurement_request.raw_request,
        "item_name": procurement_request.item_name,
        "quantity": procurement_request.quantity,
        "max_budget": procurement_request.max_budget,
        "status": procurement_request.status,
        "workflow_state": procurement_request.workflow_state,
        "created_at": procurement_request.created_at,
    }


@app.post("/requests/{request_id}/approve")
async def approve_procurement_request(request_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProcurementRequestDB).where(ProcurementRequestDB.id == request_id))
    procurement_request = result.scalar_one_or_none()
    if not procurement_request:
        raise HTTPException(status_code=404, detail="Procurement request not found")
    if procurement_request.status != "awaiting_approval":
        raise HTTPException(status_code=409, detail="Procurement request is not awaiting approval")
    workflow_state = dict(procurement_request.workflow_state or {})
    workflow_state.update({"purchase_order_number": f"PO-{procurement_request.id:06d}", "purchase_order_status": "draft", "status": "purchase_order_draft"})
    procurement_request.workflow_state = workflow_state
    procurement_request.status = "purchase_order_draft"
    await db.commit()
    await db.refresh(procurement_request)
    return {"id": procurement_request.id, "status": procurement_request.status, "purchase_order_number": workflow_state["purchase_order_number"], "purchase_order_status": workflow_state["purchase_order_status"]}


@app.post("/organizations")
async def create_organization(organization: CreateOrganizationRequest, db: AsyncSession = Depends(get_db)):
    new_organization = OrganizationDB(name=organization.name)
    db.add(new_organization)
    await db.commit()
    await db.refresh(new_organization)
    return {"id": str(new_organization.id), "name": new_organization.name, "created_at": new_organization.created_at}


@app.post("/companies", status_code=status.HTTP_201_CREATED)
async def create_company(payload: CompanyCreate, db: AsyncSession = Depends(get_db)):
    company = CompanyDB(name=payload.name)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return {"id": company.id, "name": company.name, "created_at": company.created_at}


@app.get("/companies")
async def list_companies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CompanyDB).order_by(CompanyDB.id.asc()))
    items = result.scalars().all()
    return {"count": len(items), "items": [{"id": item.id, "name": item.name} for item in items]}


@app.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    company = await db.get(CompanyDB, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    product = ProductDB(company_id=payload.company_id, name=payload.name, category=payload.category, unit=payload.unit)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "company_id": product.company_id, "name": product.name, "category": product.category, "unit": product.unit}


@app.get("/products")
async def list_products(company_id: int | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    query = select(ProductDB)
    if company_id is not None:
        query = query.where(ProductDB.company_id == company_id)
    result = await db.execute(query.order_by(ProductDB.id.asc()))
    items = result.scalars().all()
    return {"count": len(items), "items": [{"id": item.id, "company_id": item.company_id, "name": item.name, "category": item.category, "unit": item.unit} for item in items]}


@app.post("/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier(payload: SupplierCreate, db: AsyncSession = Depends(get_db)):
    supplier = SupplierDB(
        name=payload.name,
        contact_email=payload.contact_email,
        country=payload.country,
        reliability_score=payload.reliability_score,
        verification_score=payload.verification_score,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return {"id": supplier.id, "name": supplier.name, "contact_email": supplier.contact_email, "country": supplier.country, "reliability_score": supplier.reliability_score, "verification_score": supplier.verification_score}


@app.get("/suppliers")
async def list_suppliers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SupplierDB).order_by(SupplierDB.id.asc()))
    items = result.scalars().all()
    return {"count": len(items), "items": [{"id": item.id, "name": item.name, "country": item.country, "reliability_score": item.reliability_score, "verification_score": item.verification_score} for item in items]}


@app.post("/offers", status_code=status.HTTP_201_CREATED)
async def create_offer(payload: SupplierOfferCreate, db: AsyncSession = Depends(get_db)):
    product = await db.get(ProductDB, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    supplier = await db.get(SupplierDB, payload.supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if payload.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than zero")
    offer = SupplierOfferDB(
        supplier_id=payload.supplier_id,
        product_id=payload.product_id,
        price=payload.price,
        currency=_normalize_currency(payload.currency if hasattr(payload, "currency") else "USD"),
        lead_time_days=payload.lead_time_days,
        is_internal=payload.is_internal,
        source_url=payload.source_url,
        evidence_note=payload.evidence_note,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return {"id": offer.id, "supplier_id": offer.supplier_id, "product_id": offer.product_id, "price": offer.price, "currency": offer.currency, "lead_time_days": offer.lead_time_days, "is_internal": offer.is_internal}


@app.get("/offers")
async def list_offers(product_id: int | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    query = select(SupplierOfferDB)
    if product_id is not None:
        query = query.where(SupplierOfferDB.product_id == product_id)
    result = await db.execute(query.order_by(SupplierOfferDB.price.asc()))
    items = result.scalars().all()
    return {"count": len(items), "items": [{"id": item.id, "supplier_id": item.supplier_id, "product_id": item.product_id, "price": item.price, "currency": item.currency, "lead_time_days": item.lead_time_days, "is_internal": item.is_internal, "source_url": item.source_url, "evidence_note": item.evidence_note} for item in items]}


@app.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_procurement_case(payload: ProcurementCaseCreate, db: AsyncSession = Depends(get_db)):
    product = await db.get(ProductDB, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if payload.budget <= 0:
        raise HTTPException(status_code=400, detail="Budget must be greater than zero")
    currency = _normalize_currency(payload.currency)
    if not _is_valid_currency(currency):
        raise HTTPException(status_code=400, detail="Currency is not supported")
    case = ProcurementCaseDB(
        company_id=payload.company_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        budget=payload.budget,
        currency=currency,
        requester_name=payload.requester_name,
        notes=payload.notes,
        status="received",
        current_stage="intake",
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return {"id": case.id, "company_id": case.company_id, "product_id": case.product_id, "quantity": case.quantity, "budget": case.budget, "currency": case.currency, "requester_name": case.requester_name, "status": case.status, "current_stage": case.current_stage}


@app.get("/cases")
async def list_cases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProcurementCaseDB).order_by(ProcurementCaseDB.id.desc()))
    items = result.scalars().all()
    return {"count": len(items), "items": [{"id": item.id, "company_id": item.company_id, "product_id": item.product_id, "quantity": item.quantity, "budget": item.budget, "currency": item.currency, "requester_name": item.requester_name, "status": item.status, "current_stage": item.current_stage} for item in items]}


@app.get("/cases/{case_id}")
async def get_case(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    return {"id": case.id, "company_id": case.company_id, "product_id": case.product_id, "quantity": case.quantity, "budget": case.budget, "currency": case.currency, "requester_name": case.requester_name, "status": case.status, "current_stage": case.current_stage, "notes": case.notes}


@app.post("/cases/{case_id}/source")
async def source_case_offers(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    offers = await _get_offer_candidates(case, db)
    internal_offers = [offer for offer in offers if offer.is_internal]
    eligible = internal_offers if internal_offers else offers
    case.current_stage = "sourcing"
    case.status = "sourcing"
    if not eligible:
        await db.commit()
        return {"case_id": case.id, "status": "no_valid_offers", "message": "No internal offers matched this product. Local demo mode kept sourcing open without external discovery.", "offers": []}
    await db.commit()
    return {"case_id": case.id, "status": "sourcing_complete", "offers": [{"id": offer.id, "supplier_id": offer.supplier_id, "price": offer.price, "currency": offer.currency, "lead_time_days": offer.lead_time_days, "is_internal": offer.is_internal} for offer in eligible]}


@app.post("/cases/{case_id}/evaluate")
async def evaluate_case_offers(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    offers = await _get_offer_candidates(case, db)
    eligible = []
    for offer in offers:
        if offer.currency != case.currency:
            continue
        if offer.price <= case.budget:
            supplier = await db.get(SupplierDB, offer.supplier_id)
            if supplier and supplier.verification_score > 0 and supplier.reliability_score > 0:
                score = (supplier.verification_score * 0.6) + (supplier.reliability_score * 0.4)
                eligible.append({"offer_id": offer.id, "supplier_id": supplier.id, "supplier_name": supplier.name, "price": offer.price, "currency": offer.currency, "score": round(score, 4)})
    if not eligible:
        case.current_stage = "evaluation"
        case.status = "no_supplier"
        await db.commit()
        return {"case_id": case.id, "status": "no_valid_supplier", "offers": []}
    best = sorted(eligible, key=lambda item: item["price"])[0]
    case.current_stage = "evaluation"
    case.status = "evaluated"
    await db.commit()
    return {"case_id": case.id, "status": "evaluated", "selected_offer": best, "offers": eligible}


@app.post("/cases/{case_id}/rfq-draft")
async def generate_rfq_draft(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    offers = await _get_offer_candidates(case, db)
    if not offers:
        raise HTTPException(status_code=400, detail="No supplier offers available for draft generation")
    best_offer = min(offers, key=lambda offer: offer.price)
    supplier = await db.get(SupplierDB, best_offer.supplier_id)
    draft = (
        f"RFQ Draft (not sent): Request for {case.quantity} units of product {case.product_id} from {supplier.name if supplier else 'selected supplier'}. "
        f"Target budget is {case.budget} {case.currency}. Confirm price {best_offer.price} {best_offer.currency}, lead time {best_offer.lead_time_days} days. "
        f"This is a draft and requires approval before any order is issued."
    )
    case.current_stage = "negotiation"
    case.status = "draft_ready"
    await db.commit()
    return {"case_id": case.id, "status": "draft_ready", "draft": draft, "supplier_id": best_offer.supplier_id, "offer_id": best_offer.id}


@app.post("/cases/{case_id}/approve")
async def approve_case(case_id: int, payload: ApprovalAction, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    if payload.approver_name == case.requester_name:
        raise HTTPException(status_code=400, detail="Requester cannot approve their own request")
    existing_result = await db.execute(select(ApprovalDecisionDB).where(ApprovalDecisionDB.case_id == case.id).limit(1))
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {"case_id": case.id, "status": case.status, "approval": {"approver_name": existing.approver_name, "decision": existing.decision, "reason": existing.reason}}
    if payload.decision.lower() not in {"approved", "approve"}:
        raise HTTPException(status_code=400, detail="Approval requires an approved decision")
    approval = ApprovalDecisionDB(
        case_id=case.id,
        approver_name=payload.approver_name,
        requester_name=case.requester_name,
        decision="approved",
        reason=payload.reason,
    )
    case.status = "approved"
    case.current_stage = "approval"
    db.add(approval)
    offers = await _get_offer_candidates(case, db)
    if not offers:
        raise HTTPException(status_code=400, detail="No supplier offer available to create a purchase order")
    selected_offer = min(offers, key=lambda offer: offer.price)
    existing_po_result = await db.execute(select(PurchaseOrderDB).where(PurchaseOrderDB.case_id == case.id).limit(1))
    if existing_po_result.scalar_one_or_none() is None:
        po = PurchaseOrderDB(
            case_id=case.id,
            supplier_id=selected_offer.supplier_id,
            product_id=case.product_id,
            quantity=case.quantity,
            unit_price=selected_offer.price,
            currency=selected_offer.currency,
            total_price=selected_offer.price * case.quantity,
            status="issued",
        )
        db.add(po)
        case.status = "po_created"
        case.current_stage = "purchase_order"
    await db.commit()
    await db.refresh(approval)
    return {"case_id": case.id, "status": case.status, "approval": {"approver_name": approval.approver_name, "decision": approval.decision, "reason": approval.reason}, "message": "Approval recorded and subsequent workflow resumed."}


@app.post("/cases/{case_id}/reject")
async def reject_case(case_id: int, payload: ApprovalAction, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    if payload.approver_name == case.requester_name:
        raise HTTPException(status_code=400, detail="Requester cannot reject their own request")
    existing_result = await db.execute(select(ApprovalDecisionDB).where(ApprovalDecisionDB.case_id == case.id).limit(1))
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {"case_id": case.id, "status": case.status, "decision": existing.decision, "message": "A decision already exists for this case."}
    decision = ApprovalDecisionDB(
        case_id=case.id,
        approver_name=payload.approver_name,
        requester_name=case.requester_name,
        decision="rejected",
        reason=payload.reason,
    )
    case.status = "rejected"
    case.current_stage = "approval"
    db.add(decision)
    await db.commit()
    return {"case_id": case.id, "status": "rejected", "decision": "rejected", "message": "Request rejected; no purchase order was created."}


@app.get("/cases/{case_id}/workflow")
async def get_case_workflow(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await _get_case_or_404(case_id, db)
    return await _generate_workflow_summary(case, db)


@app.post("/purchase-orders/{po_id}/delivery")
async def update_delivery_status(po_id: int, payload: DeliveryUpdate, db: AsyncSession = Depends(get_db)):
    po = await db.get(PurchaseOrderDB, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    status_value = payload.status.strip().lower()
    valid = {"pending", "in_transit", "delivered", "delayed", "received"}
    if status_value not in valid:
        raise HTTPException(status_code=400, detail="Unsupported delivery status")
    update = DeliveryUpdateDB(po_id=po.id, status=status_value, updated_by=payload.updated_by, notes=payload.notes)
    db.add(update)
    po.status = status_value
    await db.commit()
    return {"po_id": po.id, "status": status_value, "updated_by": payload.updated_by, "notes": payload.notes}


@app.post("/demo/reset")
async def reset_demo_data(db: AsyncSession = Depends(get_db)):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    for model in [DeliveryUpdateDB, PurchaseOrderDB, ApprovalDecisionDB, ProcurementCaseDB, SupplierOfferDB, ProductDB, SupplierDB, CompanyDB, ProcurementRequestDB]:
        await db.execute(delete(model))
    await db.commit()

    company = CompanyDB(name="Northwind Labs")
    db.add(company)
    await db.commit()
    await db.refresh(company)

    product = ProductDB(company_id=company.id, name="Laptop Workstation", category="IT Equipment", unit="unit")
    db.add(product)
    await db.commit()
    await db.refresh(product)

    supplier = SupplierDB(name="Demo Supplier Co.", contact_email="demo@example.com", country="US", reliability_score=0.93, verification_score=0.89)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    offer = SupplierOfferDB(supplier_id=supplier.id, product_id=product.id, price=1200.0, currency="USD", lead_time_days=7, is_internal=True, source_url="https://demo.local/catalog", evidence_note="Demo inventory, locally seeded for presentation.")
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    case = ProcurementCaseDB(
        company_id=company.id,
        product_id=product.id,
        quantity=5,
        budget=7000,
        currency="USD",
        requester_name="Alicia",
        notes="Demo procurement case",
        status="received",
        current_stage="intake",
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return {"message": "Demo catalog reset complete.", "company_id": company.id, "product_id": product.id, "supplier_id": supplier.id, "offer_id": offer.id, "case_id": case.id}
