from __future__ import annotations

from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import SessionLocal
from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.models.quote import Quote
from app.models.supplier import Supplier
from app.models.workflow_event import WorkflowEvent
from app.services.adapters import (
    DemoERPAdapter,
    DemoLogisticsAdapter,
    DemoRFQAdapter,
    create_llm_gateway,
)
from app.services.approval_agent import (
    build_approval_review,
    validate_approval_response,
)
from app.services.delivery_agent import start_delivery_tracking
from app.services.intake_agent import validate_case_request
from app.services.negotiation_agent import draft_supplier_rfq
from app.services.po_agent import create_purchase_order
from app.services.quote_agent import compare_quotations, evaluate_supplier_offers
from app.services.sourcing_agent import SourcingError, run_sourcing_agent
from app.services.workflow import ProcurementState


def _new_event(
    db,
    case_id: str,
    stage: str,
    event_type: str,
    details: dict[str, Any] | None = None,
):
    db.add(WorkflowEvent(
        id=f"EVT-{uuid4().hex[:12].upper()}",
        case_id=case_id,
        stage=stage,
        event_type=event_type,
        details=details or {},
    ))


def _save_case_state(
    session_factory: sessionmaker,
    state: ProcurementState,
    status: str,
    stage: str,
    event_type: str,
    details: dict[str, Any] | None = None,
):
    with session_factory() as db:
        case = db.get(ProcurementCase, state["case_id"])
        if case:
            case.status = status
            case.current_stage = stage
        _new_event(db, state["case_id"], stage, event_type, details)
        db.commit()


def create_procurement_graph(
    checkpointer,
    session_factory: sessionmaker = SessionLocal,
    llm_gateway: Any | None = None,
    rfq_adapter: DemoRFQAdapter | None = None,
    erp_adapter: DemoERPAdapter | None = None,
    logistics_adapter: DemoLogisticsAdapter | None = None,
):
    llm_gateway = llm_gateway or create_llm_gateway()
    rfq_adapter = rfq_adapter or DemoRFQAdapter()
    erp_adapter = erp_adapter or DemoERPAdapter()
    logistics_adapter = logistics_adapter or DemoLogisticsAdapter()

    def intake_agent(state: ProcurementState):
        validation = validate_case_request(state)
        if not validation["valid"]:
            _save_case_state(
                session_factory,
                state,
                "CLARIFICATION_REQUIRED",
                "INTAKE",
                "intake_rejected",
                {"error": validation["error"]},
            )
            return {
                "status": "CLARIFICATION_REQUIRED",
                "current_stage": "INTAKE",
                "error": validation["error"],
            }

        analysis = llm_gateway.analyze_request(state)
        _save_case_state(
            session_factory,
            state,
            "INTAKE_COMPLETE",
            "INTAKE",
            "intake_validated",
            analysis,
        )
        return {
            "status": "INTAKE_COMPLETE",
            "current_stage": "INTAKE",
            "intake_summary": validation["intake_summary"],
            "request_analysis": analysis,
        }

    def after_intake(state: ProcurementState):
        return (
            END
            if state.get("status") == "CLARIFICATION_REQUIRED"
            else "supplier_sourcing_agent"
        )

    def supplier_sourcing_agent(state: ProcurementState):
        try:
            with session_factory() as db:
                source, offers = run_sourcing_agent(state, db)
        except SourcingError as error:
            _save_case_state(
                session_factory,
                state,
                "SOURCING_FAILED",
                "SOURCING",
                "sourcing_failed",
                {"error": str(error)},
            )
            return {
                "status": "SOURCING_FAILED",
                "current_stage": "SOURCING",
                "error": str(error),
                "errors": [str(error)],
            }

        if not offers:
            _save_case_state(
                session_factory,
                state,
                "NO_MATCHING_OFFERS",
                "SOURCING",
                "sourcing_no_results",
                {"source": source},
            )
            return {
                "status": "NO_MATCHING_OFFERS",
                "current_stage": "SOURCING",
                "offers": [],
            }

        offers = [
            {
                **offer,
                "supplier_id": offer.get("supplier_id"),
                "source_type": offer.get("source_type", source),
            }
            for offer in offers
        ]
        _save_case_state(
            session_factory,
            state,
            "SUPPLIERS_SHORTLISTED",
            "SOURCING",
            "suppliers_sourced",
            {
                "source": source,
                "offer_count": len(offers),
                "sources": [offer.get("source") for offer in offers],
            },
        )
        return {
            "status": "SUPPLIERS_SHORTLISTED",
            "current_stage": "SOURCING",
            "sourcing_method": source,
            "offers": offers,
        }

    def supplier_evaluation_agent(state: ProcurementState):
        evaluations = evaluate_supplier_offers(
            state.get("offers", []),
            state["budget"],
        )
        _save_case_state(
            session_factory,
            state,
            "SUPPLIERS_EVALUATED",
            "SUPPLIER_EVALUATION",
            "suppliers_evaluated",
            {
                "scores": [
                    {
                        "supplier_name": offer["supplier_name"],
                        "score": offer["evaluation_score"],
                        "verification_status": offer["verification_status"],
                    }
                    for offer in evaluations
                ]
            },
        )
        return {
            "status": "SUPPLIERS_EVALUATED",
            "current_stage": "SUPPLIER_EVALUATION",
            "supplier_evaluations": evaluations,
        }

    def quotation_analysis_agent(state: ProcurementState):
        evaluations = state.get("supplier_evaluations", [])
        if not evaluations:
            return {
                "status": "NO_MATCHING_OFFERS",
                "current_stage": "QUOTATION_ANALYSIS",
                "quote_comparison": [],
            }

        quote_comparison = compare_quotations(evaluations)

        chosen = evaluations[0]
        quote_ids = []
        selected_quote_id = None
        with session_factory() as db:
            existing_approval = db.scalar(
                select(Approval).where(Approval.case_id == state["case_id"])
            )
            existing_quotes = db.scalars(
                select(Quote).where(Quote.case_id == state["case_id"])
            ).all()
            existing_selected_quote = next(
                (quote for quote in existing_quotes if quote.status == "SELECTED"),
                None,
            )
            if existing_approval and existing_selected_quote:
                return {
                    "status": "QUOTE_ANALYZED",
                    "current_stage": "QUOTATION_ANALYSIS",
                    "quote_comparison": quote_comparison,
                    "selected_offer": chosen,
                    "quote_ids": [quote.id for quote in existing_quotes],
                    "selected_quote_id": existing_selected_quote.id,
                    "approval_id": existing_approval.id,
                }

            for offer in evaluations:
                supplier = db.scalar(
                    select(Supplier).where(
                        Supplier.company_id == state["company_id"],
                        Supplier.name == offer["supplier_name"],
                    )
                )
                if not supplier:
                    supplier = Supplier(
                        id=f"SUP-{uuid4().hex[:8].upper()}",
                        company_id=state["company_id"],
                        name=offer["supplier_name"],
                        website=offer.get("source"),
                        reliability_score=offer.get("reliability_score", 0),
                        verification_status=offer.get(
                            "verification_status", "UNVERIFIED"
                        ),
                        discovery_source=offer.get("source_type", "external").upper(),
                    )
                    db.add(supplier)
                    db.flush()

                quote = Quote(
                    id=f"Q-{uuid4().hex[:8].upper()}",
                    case_id=state["case_id"],
                    company_id=state["company_id"],
                    supplier_id=supplier.id,
                    product_name=state["product_name"],
                    quantity=state["quantity"],
                    unit_price=offer["unit_price"],
                    total_price=offer["total_price"],
                    currency=offer["currency"],
                    delivery_days=offer.get("lead_time_days"),
                    notes=(
                        f"Source: {offer.get('source', 'internal catalog')}\n"
                        f"Price evidence: {offer.get('price_evidence', 'Internal supplier catalog')}\n"
                        f"Evaluation score: {offer['evaluation_score']}/100\n"
                        f"Verification: {offer['verification_status']}"
                    ),
                    status="SELECTED" if offer is chosen else "ALTERNATIVE",
                )
                db.add(quote)
                quote_ids.append(quote.id)
                if offer is chosen:
                    selected_quote_id = quote.id

            approval = Approval(
                id=f"APP-{uuid4().hex[:8].upper()}",
                case_id=state["case_id"],
                company_id=state["company_id"],
                requested_by=state.get("requested_by"),
                amount=chosen["total_price"],
                currency=chosen["currency"],
                status="PENDING",
                comments="Review the selected evaluated offer before purchase.",
            )
            db.add(approval)
            _new_event(
                db,
                state["case_id"],
                "QUOTATION_ANALYSIS",
                "quotes_compared",
                {
                    "selected_supplier": chosen["supplier_name"],
                    "selected_total": chosen["total_price"],
                    "currency": chosen["currency"],
                    "offer_count": len(evaluations),
                    "approval_id": approval.id,
                },
            )
            case = db.get(ProcurementCase, state["case_id"])
            if case:
                case.status = "QUOTE_ANALYZED"
                case.current_stage = "QUOTATION_ANALYSIS"
            db.commit()
            approval_id = approval.id

        return {
            "status": "QUOTE_ANALYZED",
            "current_stage": "QUOTATION_ANALYSIS",
            "quote_comparison": quote_comparison,
            "selected_offer": chosen,
            "quote_ids": quote_ids,
            "selected_quote_id": selected_quote_id or "",
            "approval_id": approval_id,
        }

    def negotiation_agent(state: ProcurementState):
        gateway_result = state.get("request_analysis", {})
        drafts = []
        for offer in state.get("supplier_evaluations", []):
            drafts.append(
                draft_supplier_rfq(offer, state, llm_gateway, rfq_adapter)
            )
        _save_case_state(
            session_factory,
            state,
            "NEGOTIATION_DRAFTED",
            "NEGOTIATION",
            "negotiation_drafts_prepared",
            {
                "provider": gateway_result.get("model_provider", "local-demo"),
                "draft_count": len(drafts),
                "delivery_status": "NOT_SENT",
            },
        )
        return {
            "status": "NEGOTIATION_DRAFTED",
            "current_stage": "NEGOTIATION",
            "negotiation_drafts": drafts,
        }

    def prepare_approval_agent(state: ProcurementState):
        _save_case_state(
            session_factory,
            state,
            "PENDING_APPROVAL",
            "APPROVAL",
            "human_approval_requested",
            {
                "approval_id": state["approval_id"],
                "selected_quote_id": state["selected_quote_id"],
            },
        )
        return {
            "status": "PENDING_APPROVAL",
            "current_stage": "APPROVAL",
        }

    def approval_interrupt_agent(state: ProcurementState):
        review = build_approval_review(state)
        response = validate_approval_response(interrupt(review))
        return response

    def after_approval(state: ProcurementState):
        return (
            "purchase_order_agent"
            if state.get("decision") == "approve"
            else "approval_rejection_agent"
        )

    def approval_decision_agent(state: ProcurementState):
        with session_factory() as db:
            approval = db.get(Approval, state["approval_id"])
            case = db.get(ProcurementCase, state["case_id"])
            if approval:
                approval.status = "APPROVED"
                approval.approved_by = state["approved_by"]
                approval.comments = state.get("approval_comment") or approval.comments
            if case:
                case.status = "APPROVED"
                case.current_stage = "APPROVED"
            _new_event(
                db,
                state["case_id"],
                "APPROVAL",
                "human_approved",
                {
                    "approved_by": state["approved_by"],
                    "approval_id": state["approval_id"],
                    "comment": state.get("approval_comment"),
                },
            )
            db.commit()
        return {"status": "APPROVED", "current_stage": "APPROVED"}

    def approval_rejection_agent(state: ProcurementState):
        with session_factory() as db:
            approval = db.get(Approval, state["approval_id"])
            case = db.get(ProcurementCase, state["case_id"])
            if approval:
                approval.status = "REJECTED"
                approval.approved_by = state["approved_by"]
                approval.comments = state.get("approval_comment") or approval.comments
            if case:
                case.status = "REJECTED"
                case.current_stage = "REJECTED"
            _new_event(
                db,
                state["case_id"],
                "APPROVAL",
                "human_rejected",
                {
                    "approved_by": state["approved_by"],
                    "approval_id": state["approval_id"],
                    "comment": state.get("approval_comment"),
                },
            )
            db.commit()
        return {"status": "REJECTED", "current_stage": "REJECTED"}

    def purchase_order_agent(state: ProcurementState):
        with session_factory() as db:
            purchase_order, erp_result = create_purchase_order(
                db,
                state,
                erp_adapter,
            )
            _new_event(
                db,
                state["case_id"],
                "PURCHASE_ORDER",
                "purchase_order_generated",
                erp_result,
            )
            db.commit()
            po_id = purchase_order.id
        return {
            "po_id": po_id,
            "status": "PO_GENERATED",
            "current_stage": "PURCHASE_ORDER",
        }

    def delivery_tracking_agent(state: ProcurementState):
        with session_factory() as db:
            delivery_record, tracking = start_delivery_tracking(
                db,
                state,
                logistics_adapter,
            )
            _new_event(
                db,
                state["case_id"],
                "DELIVERY_TRACKING",
                "tracking_initialized",
                tracking,
            )
            db.commit()
            delivery_id = delivery_record.id
        return {
            "delivery_id": delivery_id,
            "tracking_reference": tracking.get("tracking_reference"),
            "tracking_status": tracking["status"],
            "tracking_provider": tracking["provider"],
            "status": "DELIVERY_IN_PROGRESS",
            "current_stage": "DELIVERY_TRACKING",
        }

    graph = StateGraph(ProcurementState)
    graph.add_node("intake_agent", intake_agent)
    graph.add_node("supplier_sourcing_agent", supplier_sourcing_agent)
    graph.add_node("supplier_evaluation_agent", supplier_evaluation_agent)
    graph.add_node("quotation_analysis_agent", quotation_analysis_agent)
    graph.add_node("negotiation_agent", negotiation_agent)
    graph.add_node("prepare_approval_agent", prepare_approval_agent)
    graph.add_node("approval_interrupt_agent", approval_interrupt_agent)
    graph.add_node("approval_decision_agent", approval_decision_agent)
    graph.add_node("approval_rejection_agent", approval_rejection_agent)
    graph.add_node("purchase_order_agent", purchase_order_agent)
    graph.add_node("delivery_tracking_agent", delivery_tracking_agent)

    graph.add_edge(START, "intake_agent")
    graph.add_conditional_edges(
        "intake_agent",
        after_intake,
        {"supplier_sourcing_agent": "supplier_sourcing_agent", END: END},
    )
    graph.add_conditional_edges(
        "supplier_sourcing_agent",
        lambda state: (
            END
            if state.get("status") in {"SOURCING_FAILED", "NO_MATCHING_OFFERS"}
            else "supplier_evaluation_agent"
        ),
        {
            "supplier_evaluation_agent": "supplier_evaluation_agent",
            END: END,
        },
    )
    graph.add_edge("supplier_evaluation_agent", "quotation_analysis_agent")
    graph.add_edge("quotation_analysis_agent", "negotiation_agent")
    graph.add_edge("negotiation_agent", "prepare_approval_agent")
    graph.add_edge("prepare_approval_agent", "approval_interrupt_agent")
    graph.add_conditional_edges(
        "approval_interrupt_agent",
        after_approval,
        {
            "purchase_order_agent": "approval_decision_agent",
            "approval_rejection_agent": "approval_rejection_agent",
        },
    )
    graph.add_edge("approval_decision_agent", "purchase_order_agent")
    graph.add_edge("purchase_order_agent", "delivery_tracking_agent")
    graph.add_edge("delivery_tracking_agent", END)
    graph.add_edge("approval_rejection_agent", END)

    return graph.compile(checkpointer=checkpointer)


def workflow_config(case_id: str):
    return {"configurable": {"thread_id": case_id}}


def workflow_summary(graph, case_id: str):
    snapshot = graph.get_state(workflow_config(case_id))
    state = snapshot.values or {}
    interrupts = []
    for task in snapshot.tasks:
        for item in task.interrupts:
            interrupts.append(item.value)
    return {
        "case_id": case_id,
        "status": state.get("status"),
        "current_stage": state.get("current_stage"),
        "next_nodes": list(snapshot.next),
        "paused_for_approval": bool(interrupts),
        "interrupts": interrupts,
        "state": state,
    }
