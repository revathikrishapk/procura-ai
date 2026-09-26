from app.services.workflow import CaseState

def run_intake(state: dict) -> dict:
    required_fields=[
        "title",
        "description",
        "quantity",
        "budget"
    ]

    missing_fields=[]

    for field in required_fields:
        if not state.get(field):
            missing_fields.append(field)

    if missing_fields:

        return {
            "status": CaseState.CLARIFICATION_REQUIRED,
            "error":(
                "Missing fields: "
                + ", ".join(missing_fields)
            )
        }
    summary=(
        f"Procurement request for"
        f"{state['quantity']} units of"
        f"{state['title']}"
        f"with a budget of "
        f"Rs.{state['budget']:,.2f}"
    )

    return {
        "status":CaseState.INTAKE_COMPLETE,

        "intake_summary":summary
    }