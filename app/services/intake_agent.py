from app.services.workflow import CaseState


def validate_case_request(state: dict) -> dict:
    required_fields = [
        "company_id",
        "product_name",
        "quantity",
        "budget",
    ]

    missing_fields = []
    for field in required_fields:
        value = state.get(field)
        if value in (None, "", [], {}):
            missing_fields.append(field)

    if missing_fields:
        return {
            "valid": False,
            "status": CaseState.CLARIFICATION_REQUIRED,
            "missing_fields": missing_fields,
            "error": "Missing fields: " + ", ".join(missing_fields),
        }

    if int(state.get("quantity", 0)) <= 0:
        return {
            "valid": False,
            "status": CaseState.CLARIFICATION_REQUIRED,
            "missing_fields": ["quantity"],
            "error": "Quantity must be greater than zero.",
        }

    if float(state.get("budget", 0)) <= 0:
        return {
            "valid": False,
            "status": CaseState.CLARIFICATION_REQUIRED,
            "missing_fields": ["budget"],
            "error": "Budget must be greater than zero.",
        }

    summary = (
        f"Procurement request for {state['quantity']} units of {state['product_name']} "
        f"with a budget of Rs.{float(state['budget']):,.2f}"
    )

    return {
        "valid": True,
        "status": CaseState.INTAKE_COMPLETE,
        "intake_summary": summary,
        "missing_fields": [],
    }


def run_intake(state: dict) -> dict:
    return validate_case_request(state)