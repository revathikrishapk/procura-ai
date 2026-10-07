from typing import Any


def build_approval_review(state: dict[str, Any]):
    return {
        "type": "procurement_approval",
        "case_id": state["case_id"],
        "approval_id": state["approval_id"],
        "selected_offer": state["selected_offer"],
        "quote_comparison": state["quote_comparison"],
        "negotiation_drafts": state.get("negotiation_drafts", []),
        "warning": "Negotiation/RFQ drafts have not been sent to any supplier.",
    }


def validate_approval_response(response):
    if not isinstance(response, dict) or response.get("decision") not in {
        "approve",
        "reject",
    }:
        raise ValueError("Approval response must have decision approve or reject.")

    approver = response.get("approved_by")
    if not isinstance(approver, str) or not approver.strip():
        raise ValueError("An approver name is required.")
    return {
        "decision": response["decision"],
        "approved_by": approver.strip(),
        "approval_comment": response.get("comments", ""),
    }