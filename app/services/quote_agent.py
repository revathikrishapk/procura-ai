from __future__ import annotations

from typing import Any


def evaluate_supplier_offers(
    offers: list[dict[str, Any]],
    budget: float,
) -> list[dict[str, Any]]:
    evaluations = []
    for offer in offers:
        verification = str(offer.get("verification_status", "UNVERIFIED")).upper()
        reliability = float(offer.get("reliability_score", 0) or 0)
        price_ratio = float(offer["total_price"]) / float(budget) if budget else 1
        price_score = max(0, 60 * (1 - price_ratio))
        reliability_score = max(0, min(25, reliability * 25))
        verified_score = 10 if verification == "VERIFIED" else 0
        lead_days = offer.get("lead_time_days")
        lead_score = (
            max(0, 15 * (1 - min(int(lead_days), 60) / 60))
            if lead_days
            else 0
        )
        evaluations.append({
            **offer,
            "verification_status": verification,
            "evaluation_score": round(
                price_score + reliability_score + verified_score + lead_score,
                2,
            ),
            "evaluation_factors": {
                "price_score": round(price_score, 2),
                "reliability_score": round(reliability_score, 2),
                "verification_score": verified_score,
                "lead_time_score": round(lead_score, 2),
            },
            "evaluation_notice": (
                "Supplier is not verified in the company directory."
                if verification != "VERIFIED"
                else "Supplier is verified in the company directory."
            ),
        })

    return sorted(
        evaluations,
        key=lambda offer: (
            -offer["evaluation_score"],
            offer["total_price"],
        ),
    )


def compare_quotations(evaluations: list[dict[str, Any]]):
    return [
        {
            "supplier_name": offer["supplier_name"],
            "unit_price": offer["unit_price"],
            "total_price": offer["total_price"],
            "currency": offer["currency"],
            "lead_time_days": offer.get("lead_time_days"),
            "evaluation_score": offer["evaluation_score"],
            "verification_status": offer["verification_status"],
            "source": offer.get("source"),
            "price_evidence": offer.get("price_evidence"),
        }
        for offer in evaluations
    ]