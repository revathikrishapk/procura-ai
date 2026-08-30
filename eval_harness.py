import asyncio
from app.agents.graph import create_workflow
from app.agents.state import ProcurementState

# 1. Test Dataset (Includes clean cases + ambiguity traps)
TEST_CASES = [
    {
        "id": "TC-01",
        "input": "Need 10 MacBooks for new hires, max budget $20,000 within 5 days.",
        "expect_ambiguous": False,
    },
    {
        "id": "TC-02",
        "input": "Order 5 monitors ASAP.",  # TRAP: Missing budget
        "expect_ambiguous": True,
    },
    {
        "id": "TC-03",
        "input": "We need Dell laptops, budget is 15k.",  # TRAP: Missing quantity
        "expect_ambiguous": True,
    },
    {
        "id": "TC-04",
        "input": "Buy 50 ergonomic chairs, under $10,000, deliver in 14 days.",
        "expect_ambiguous": False,
    },
    {
        "id": "TC-05",
        "input": "Procure cloud server credits.",  # TRAP: Missing budget & quantity
        "expect_ambiguous": True,
    }
]

async def run_harness():
    # Compile graph without checkpointer for evaluation test runs
    app = create_workflow().compile()
    results = []

    for tc in TEST_CASES:
        initial_state: ProcurementState = {
            "raw_request": tc["input"],
            "request_spec": {},
            "quotes": [],
            "comparison": {},
            "is_ambiguous": False,
            "error": None
        }

        # Invoke the complete compiled graph
        final_state = await app.ainvoke(initial_state)

        # 1. Parse check: Were key fields extracted?
        spec = final_state.get("request_spec", {})
        parsed_valid = bool(spec.get("item_name") and (spec.get("quantity") or final_state["is_ambiguous"]))
        
        # 2. Ambiguity check: Did the model accurately classify ambiguity?
        ambiguity_handled = (final_state["is_ambiguous"] == tc["expect_ambiguous"])

        # 3. Downstream check: Did valid cases reach comparison, and ambiguous cases halt safely?
        if tc["expect_ambiguous"]:
            downstream_usable = final_state["is_ambiguous"] and (not final_state["quotes"])
        else:
            downstream_usable = final_state.get("comparison", {}).get("fits_budget", False)

        results.append({
            "id": tc["id"],
            "parsed_valid": parsed_valid,
            "ambiguity_handled": ambiguity_handled,
            "downstream_usable": downstream_usable,
            "error": final_state.get("error")
        })

    # Metrics Calculation
    total = len(results)
    parsed_pct = (sum(1 for r in results if r["parsed_valid"]) / total) * 100
    usable_pct = (sum(1 for r in results if r["downstream_usable"]) / total) * 100
    trap_pct = (sum(1 for r in results if r["ambiguity_handled"]) / total) * 100

    print("\n================ EVALUATION HARNESS RESULTS ================")
    print(f"Total Test Cases Processed          : {total}")
    print(f"Valid RequestSpec Parse Rate         : {parsed_pct:.1f}%")
    print(f"Usable Downstream Output Rate       : {usable_pct:.1f}%")
    print(f"Ambiguity Trap Handling Pass Rate   : {trap_pct:.1f}%")
    print("============================================================\n")

    for r in results:
        status = "PASS" if (r["parsed_valid"] and r["ambiguity_handled"] and r["downstream_usable"]) else "FAIL"
        print(f"[{status}] {r['id']} | Error: {r['error'] or 'None'}")

if __name__ == "__main__":
    asyncio.run(run_harness())