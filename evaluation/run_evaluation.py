"""Run the isolated, synthetic supplier-selection benchmark.

The benchmark calls Procura's real internal-offer query/filter and supplier
scoring functions. Its separate price-only selector is evaluation-only.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
from app.models.approval import Approval
from app.models.case import ProcurementCase
from app.models.company import Company
from app.models.po import PurchaseOrder
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.models.quote import Quote
from app.services.adapters import DemoLLMGateway
from app.services.database_service import find_internal_supplier_offers
from app.services.langgraph_workflow import (
    create_procurement_graph,
    workflow_config,
    workflow_summary,
)
from app.services.quote_agent import evaluate_supplier_offers

EVALUATION_DIR = ROOT / "evaluation"
DATASET_PATH = EVALUATION_DIR / "benchmark_dataset.csv"
RESULTS_DIR = EVALUATION_DIR / "results"
FIGURES_DIR = EVALUATION_DIR / "figures"
COMPANY_ID = "SYNTHETIC-BENCHMARK"


def read_dataset() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with DATASET_PATH.open(newline="", encoding="utf-8-sig") as dataset_file:
        for row in csv.DictReader(dataset_file):
            row["quantity"] = int(row["quantity"])
            row["budget"] = float(row["budget"])
            row["unit_price"] = (
                float(row["unit_price"].strip())
                if row["unit_price"].strip()
                else None
            )
            row["reliability_score"] = float(row["reliability_score"])
            row["lead_time_days"] = (
                int(row["lead_time_days"].strip())
                if row["lead_time_days"].strip()
                else None
            )
            for field in (
                "supplier_name",
                "currency",
                "verification_status",
                "source",
                "source_evidence",
                "price_evidence",
            ):
                row[field] = row[field].strip()
            row["total_price"] = (
                row["unit_price"] * row["quantity"]
                if row["unit_price"] is not None
                else None
            )
            cases[row["case_id"]].append(row)

    if len(cases) < 20:
        raise ValueError(f"Expected at least 20 benchmark cases; found {len(cases)}.")
    for case_id, offers in cases.items():
        first = offers[0]
        if any(
            (offer[field] != first[field])
            for offer in offers
            for field in (
                "scenario",
                "product_name",
                "quantity",
                "budget",
                "approval_decision",
            )
        ):
            raise ValueError(f"Case-level fields differ within {case_id}.")
    return [offers[0] for offers in cases.values()], dict(cases)


def seed_database(
    Session: sessionmaker,
    case_rows: list[dict[str, Any]],
    offers_by_case: dict[str, list[dict[str, Any]]],
) -> None:
    with Session() as db:
        db.add(Company(id=COMPANY_ID, name="Synthetic Evaluation Company"))
        for case in case_rows:
            db.add(Product(
                id=f"PRODUCT-{case['case_id']}",
                company_id=COMPANY_ID,
                name=case["product_name"],
                category="Synthetic benchmark",
            ))
            for offer in offers_by_case[case["case_id"]]:
                db.add(Supplier(
                    id=offer["supplier_id"],
                    company_id=COMPANY_ID,
                    name=offer["supplier_name"],
                    website=offer["source"] or None,
                    reliability_score=offer["reliability_score"],
                    verification_status=offer["verification_status"],
                    discovery_source="INTERNAL",
                ))
                db.add(SupplierProduct(
                    id=f"SP-{offer['supplier_id']}",
                    company_id=COMPANY_ID,
                    supplier_id=offer["supplier_id"],
                    product_id=f"PRODUCT-{case['case_id']}",
                    last_price=offer["unit_price"],
                    currency=offer["currency"],
                    lead_time_days=offer["lead_time_days"],
                    source=offer["source"],
                ))
            db.add(ProcurementCase(
                id=case["case_id"],
                company_id=COMPANY_ID,
                requested_by="Synthetic benchmark reviewer",
                product_name=case["product_name"],
                quantity=case["quantity"],
                budget=case["budget"],
                currency=case["currency"],
                status="REQUEST_SUBMITTED",
                current_stage="INTAKE",
            ))
        db.commit()


def source_candidates(
    Session: sessionmaker,
    case: dict[str, Any],
) -> list[dict[str, Any]]:
    with Session() as db:
        return find_internal_supplier_offers(
            COMPANY_ID,
            case["product_name"],
            case["quantity"],
            case["budget"],
            case["currency"],
            db,
        )


def price_only_baseline(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluation-only baseline: ascending price, then stable identity tie-break."""
    return sorted(
        offers,
        key=lambda offer: (
            float(offer["total_price"]),
            str(offer.get("supplier_name") or "").casefold(),
            str(offer["supplier_id"]),
        ),
    )


def reference_ranking(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Independent risk-first rubric, not either compared algorithm."""
    def key(offer: dict[str, Any]) -> tuple[Any, ...]:
        name = str(offer.get("supplier_name") or "").strip()
        reliability = float(offer.get("reliability_score") or 0)
        identity_invalid = not name or not 0 <= reliability <= 1
        verified = str(offer.get("verification_status") or "").upper() == "VERIFIED"
        lead_days = offer.get("lead_time_days")
        return (
            identity_invalid,
            not verified,
            -reliability,
            int(lead_days) if lead_days is not None else math.inf,
            float(offer["total_price"]),
            name.casefold(),
            str(offer["supplier_id"]),
        )

    return sorted(offers, key=key)


def spearman_rho(
    ranking: list[dict[str, Any]],
    reference: list[dict[str, Any]],
) -> float | None:
    if len(reference) < 2:
        return None
    reference_rank = {
        offer["supplier_id"]: index + 1
        for index, offer in enumerate(reference)
    }
    observed = {
        offer["supplier_id"]: index + 1
        for index, offer in enumerate(ranking)
    }
    if set(reference_rank) != set(observed):
        raise ValueError("Ranking candidates differ; comparison is not fair.")
    expected_values = [reference_rank[key] for key in reference_rank]
    observed_values = [observed[key] for key in reference_rank]
    mean_expected = statistics.mean(expected_values)
    mean_observed = statistics.mean(observed_values)
    covariance = sum(
        (expected - mean_expected) * (observed - mean_observed)
        for expected, observed in zip(expected_values, observed_values)
    )
    denominator = math.sqrt(
        sum((value - mean_expected) ** 2 for value in expected_values)
        * sum((value - mean_observed) ** 2 for value in observed_values)
    )
    return covariance / denominator if denominator else 1.0


def supplier_label(offer: dict[str, Any] | None) -> str:
    if offer is None:
        return "NONE"
    return str(offer.get("supplier_name") or "(blank supplier name)")


def rank_of_supplier(
    ranking: list[dict[str, Any]],
    supplier_id: str | None,
) -> int | None:
    if supplier_id is None:
        return None
    return next(
        (
            index
            for index, offer in enumerate(ranking, start=1)
            if offer["supplier_id"] == supplier_id
        ),
        None,
    )


def measured_selection(
    Session: sessionmaker,
    case: dict[str, Any],
    use_procura: bool,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    candidates = source_candidates(Session, case)
    ranking = (
        evaluate_supplier_offers(candidates, case["budget"])
        if use_procura
        else price_only_baseline(candidates)
    )
    return ranking, time.perf_counter() - started


def run_workflows(
    Session: sessionmaker,
    cases: list[dict[str, Any]],
    candidates_by_case: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    graph = create_procurement_graph(
        InMemorySaver(),
        session_factory=Session,
        llm_gateway=DemoLLMGateway(),
    )
    workflow_results: dict[str, dict[str, Any]] = {}

    def supplied_internal_candidates(
        state: dict[str, Any],
        _db: Any,
    ) -> tuple[str, list[dict[str, Any]]]:
        return "internal", candidates_by_case[state["case_id"]]

    with patch(
        "app.services.langgraph_workflow.run_sourcing_agent",
        side_effect=supplied_internal_candidates,
    ):
        for case in cases:
            case_id = case["case_id"]
            decision = case["approval_decision"]
            state = {
                "case_id": case_id,
                "company_id": COMPANY_ID,
                "requested_by": "Synthetic benchmark reviewer",
                "product_name": case["product_name"],
                "quantity": case["quantity"],
                "budget": case["budget"],
                "currency": case["currency"],
                "status": "REQUEST_SUBMITTED",
                "current_stage": "INTAKE",
            }
            started = time.perf_counter()
            graph.invoke(state, config=workflow_config(case_id))
            before_resume = workflow_summary(graph, case_id)
            paused = before_resume["paused_for_approval"]
            resumed = False
            if paused:
                graph.invoke(
                    Command(resume={
                        "decision": decision,
                        "approved_by": "Synthetic evaluation reviewer",
                        "comments": "Predeclared synthetic benchmark decision.",
                    }),
                    config=workflow_config(case_id),
                )
                resumed = True
            elapsed = time.perf_counter() - started
            after_resume = workflow_summary(graph, case_id)
            with Session() as db:
                approval = db.scalar(
                    select(Approval).where(Approval.case_id == case_id)
                )
                po_count = db.scalar(
                    select(func.count()).select_from(PurchaseOrder).where(
                        PurchaseOrder.case_id == case_id
                    )
                )
                quote_count = db.scalar(
                    select(func.count()).select_from(Quote).where(
                        Quote.case_id == case_id
                    )
                )
                approval_count = db.scalar(
                    select(func.count()).select_from(Approval).where(
                        Approval.case_id == case_id
                    )
                )
            expected_terminal = (
                "REJECTED" if decision == "reject" else "DELIVERY_IN_PROGRESS"
            )
            expected_approval_status = (
                "REJECTED" if decision == "reject" else "APPROVED"
            )
            applicable = bool(candidates_by_case[case_id])
            successful = (
                (
                    paused
                    and resumed
                    and after_resume["status"] == expected_terminal
                    and (approval.status if approval else None)
                    == expected_approval_status
                    and (po_count == 0 if decision == "reject" else po_count == 1)
                )
                if applicable
                else None
            )
            workflow_results[case_id] = {
                "applicable": applicable,
                "paused_for_approval": paused,
                "resumed": resumed,
                "status_before_resume": before_resume["status"],
                "status_after_resume": after_resume["status"],
                "approval_decision": decision if paused else "",
                "purchase_order_count": int(po_count or 0),
                "quote_count": int(quote_count or 0),
                "approval_count": int(approval_count or 0),
                "successful": successful,
                "elapsed_s": elapsed,
            }
    return workflow_results


def raw_evidence_coverage(
    offers_by_case: dict[str, list[dict[str, Any]]],
) -> tuple[float, int, int]:
    all_offers = [
        offer
        for offers in offers_by_case.values()
        for offer in offers
    ]
    with_evidence = sum(
        1
        for offer in all_offers
        if offer["unit_price"] is not None
        and offer["unit_price"] > 0
        and bool(offer["source_evidence"])
        and bool(offer["price_evidence"])
    )
    return (
        100.0 * with_evidence / len(all_offers),
        with_evidence,
        len(all_offers),
    )


def build_case_results(
    Session: sessionmaker,
    cases: list[dict[str, Any]],
    offers_by_case: dict[str, list[dict[str, Any]]],
    candidates_by_case: dict[str, list[dict[str, Any]]],
    workflows: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[float], list[float], list[float], list[float]]:
    results = []
    baseline_times: list[float] = []
    procura_times: list[float] = []
    baseline_rhos: list[float] = []
    procura_rhos: list[float] = []

    for case in cases:
        case_id = case["case_id"]
        baseline_ranking, baseline_time = measured_selection(
            Session, case, use_procura=False
        )
        procura_ranking, procura_time = measured_selection(
            Session, case, use_procura=True
        )
        candidates = candidates_by_case[case_id]
        reference = reference_ranking(candidates)
        expected = reference[0] if reference else None
        baseline_selected = baseline_ranking[0] if baseline_ranking else None
        procura_selected = procura_ranking[0] if procura_ranking else None
        baseline_rho = spearman_rho(baseline_ranking, reference)
        procura_rho = spearman_rho(procura_ranking, reference)
        if baseline_rho is not None:
            baseline_rhos.append(baseline_rho)
        if procura_rho is not None:
            procura_rhos.append(procura_rho)
        baseline_times.append(baseline_time)
        procura_times.append(procura_time)
        workflow = workflows[case_id]
        results.append({
            "case_id": case_id,
            "scenario": case["scenario"],
            "expected_supplier": supplier_label(expected),
            "expected_supplier_id": expected["supplier_id"] if expected else "",
            "baseline_selected_supplier": supplier_label(baseline_selected),
            "procura_selected_supplier": supplier_label(procura_selected),
            "baseline_correct": (
                baseline_selected["supplier_id"] == expected["supplier_id"]
                if expected is not None and baseline_selected is not None
                else ""
            ),
            "procura_correct": (
                procura_selected["supplier_id"] == expected["supplier_id"]
                if expected is not None and procura_selected is not None
                else ""
            ),
            "baseline_rank": rank_of_supplier(
                baseline_ranking, expected["supplier_id"] if expected else None
            ) or "",
            "procura_rank": rank_of_supplier(
                procura_ranking, expected["supplier_id"] if expected else None
            ) or "",
            "reference_ranking": " > ".join(
                supplier_label(offer) for offer in reference
            ),
            "baseline_ranking": " > ".join(
                supplier_label(offer) for offer in baseline_ranking
            ),
            "procura_ranking": " > ".join(
                supplier_label(offer) for offer in procura_ranking
            ),
            "baseline_spearman_rho": (
                f"{baseline_rho:.9f}" if baseline_rho is not None else ""
            ),
            "procura_spearman_rho": (
                f"{procura_rho:.9f}" if procura_rho is not None else ""
            ),
            "eligible_offer_count": len(candidates),
            "raw_offer_count": len(offers_by_case[case_id]),
            "budget": case["budget"],
            "baseline_budget_compliant": (
                baseline_selected["total_price"] <= case["budget"]
                if baseline_selected else ""
            ),
            "procura_budget_compliant": (
                procura_selected["total_price"] <= case["budget"]
                if procura_selected else ""
            ),
            "processing_time_baseline_s": f"{baseline_time:.9f}",
            "processing_time_procura_s": f"{procura_time:.9f}",
            "workflow_applicable": workflow["applicable"],
            "workflow_paused_for_approval": workflow["paused_for_approval"],
            "workflow_resumed": workflow["resumed"],
            "workflow_status_before_resume": workflow["status_before_resume"],
            "workflow_status_after_resume": workflow["status_after_resume"],
            "workflow_success": (
                workflow["successful"] if workflow["applicable"] else ""
            ),
            "workflow_processing_time_s": f"{workflow['elapsed_s']:.9f}",
        })
    return results, baseline_times, procura_times, baseline_rhos, procura_rhos


def safe_mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def metric_row(
    name: str,
    baseline: float | None,
    procura: float | None,
    favorable: str,
    notes: str,
    percentage: bool = False,
    improvement: bool = True,
) -> dict[str, Any]:
    difference = (
        procura - baseline
        if baseline is not None and procura is not None
        else None
    )
    if improvement and baseline not in (None, 0):
        improvement_percent = (
            (baseline - procura) / abs(baseline) * 100
            if favorable == "lower"
            else (procura - baseline) / abs(baseline) * 100
        )
    else:
        improvement_percent = None
    return {
        "metric": name,
        "price_only_baseline": (
            f"{baseline:.6f}" if baseline is not None else "N/A"
        ),
        "procura_ai": f"{procura:.6f}" if procura is not None else "N/A",
        "difference_procura_minus_baseline": (
            f"{difference:.6f}" if difference is not None else "N/A"
        ),
        "improvement_percent": (
            f"{improvement_percent:.6f}"
            if improvement_percent is not None
            else "N/A"
        ),
        "favorable_direction": favorable,
        "notes": notes,
        "_baseline_value": baseline,
        "_procura_value": procura,
        "_percentage": percentage,
    }


def calculate_metrics(
    case_rows: list[dict[str, Any]],
    offers_by_case: dict[str, list[dict[str, Any]]],
    workflow_results: dict[str, dict[str, Any]],
    baseline_times: list[float],
    procura_times: list[float],
    baseline_rhos: list[float],
    procura_rhos: list[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accuracy_rows = [
        row for row in case_rows
        if row["expected_supplier_id"]
    ]
    baseline_correct = sum(row["baseline_correct"] is True for row in accuracy_rows)
    procura_correct = sum(row["procura_correct"] is True for row in accuracy_rows)
    baseline_selected = [
        row for row in case_rows if row["baseline_selected_supplier"] != "NONE"
    ]
    procura_selected = [
        row for row in case_rows if row["procura_selected_supplier"] != "NONE"
    ]
    baseline_budget_ok = sum(
        row["baseline_budget_compliant"] is True for row in baseline_selected
    )
    procura_budget_ok = sum(
        row["procura_budget_compliant"] is True for row in procura_selected
    )
    total_evidence, evidence_count, evidence_denominator = raw_evidence_coverage(
        offers_by_case
    )
    applicable_workflows = [
        result for result in workflow_results.values() if result["applicable"]
    ]
    workflow_success = sum(result["successful"] for result in applicable_workflows)

    baseline_accuracy = 100 * baseline_correct / len(accuracy_rows)
    procura_accuracy = 100 * procura_correct / len(accuracy_rows)
    baseline_budget = (
        100 * baseline_budget_ok / len(baseline_selected)
        if baseline_selected else None
    )
    procura_budget = (
        100 * procura_budget_ok / len(procura_selected)
        if procura_selected else None
    )
    workflow_rate = (
        100 * workflow_success / len(applicable_workflows)
        if applicable_workflows else None
    )
    metrics = [
        metric_row(
            "Selection Accuracy (%)",
            baseline_accuracy,
            procura_accuracy,
            "higher",
            f"{baseline_correct}/{len(accuracy_rows)} vs "
            f"{procura_correct}/{len(accuracy_rows)} cases with at least one "
            "eligible offer; no-offer cases are not accuracy-eligible.",
            percentage=True,
        ),
        metric_row(
            "Ranking Performance (mean Spearman rho)",
            safe_mean(baseline_rhos),
            safe_mean(procura_rhos),
            "higher",
            f"Mean per-case rho across {len(baseline_rhos)} cases with at least "
            "two eligible offers; rho ranges from -1 to 1.",
            improvement=False,
        ),
        metric_row(
            "Budget Compliance (%)",
            baseline_budget,
            procura_budget,
            "higher",
            "Selected offers within stated budget divided by cases with a "
            "selected supplier; sourcing filters out-of-budget internal offers.",
            percentage=True,
        ),
        metric_row(
            "Evidence Coverage (%)",
            total_evidence,
            total_evidence,
            "higher",
            f"{evidence_count}/{evidence_denominator} raw synthetic offer rows "
            "have positive explicit prices plus non-empty source and price "
            "evidence fields. Same shared input coverage for both algorithms.",
            percentage=True,
            improvement=False,
        ),
        metric_row(
            "Workflow Success Rate (%)",
            None,
            workflow_rate,
            "higher",
            f"{workflow_success}/{len(applicable_workflows)} eligible end-to-end "
            "workflow cases reached the expected post-interrupt terminal state. "
            "Price-only baseline has no workflow.",
            percentage=True,
            improvement=False,
        ),
        metric_row(
            "Average Processing Time (seconds; lower is better)",
            safe_mean(baseline_times),
            safe_mean(procura_times),
            "lower",
            "Per-case elapsed wall time for the same internal sourcing/filter "
            "query plus each selector; excludes database seeding and workflow.",
            improvement=True,
        ),
    ]
    summary = {
        "case_count": len(case_rows),
        "accuracy_case_count": len(accuracy_rows),
        "baseline_correct": baseline_correct,
        "procura_correct": procura_correct,
        "ranking_case_count": len(baseline_rhos),
        "baseline_budget_cases": len(baseline_selected),
        "procura_budget_cases": len(procura_selected),
        "evidence_covered_offers": evidence_count,
        "evidence_offer_count": evidence_denominator,
        "workflow_applicable_cases": len(applicable_workflows),
        "workflow_successes": workflow_success,
        "baseline_total_processing_s": sum(baseline_times),
        "procura_total_processing_s": sum(procura_times),
        "baseline_times": baseline_times,
        "procura_times": procura_times,
        "workflow_times": [
            item["elapsed_s"] for item in applicable_workflows
        ],
    }
    return metrics, summary


def time_summary(values: list[float]) -> str:
    if not values:
        return "N/A"
    stddev = statistics.stdev(values) if len(values) > 1 else 0.0
    return (
        f"mean={statistics.mean(values):.9f}s; "
        f"median={statistics.median(values):.9f}s; "
        f"sample SD={stddev:.9f}s; min={min(values):.9f}s; "
        f"max={max(values):.9f}s; n={len(values)}"
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty result file: {path}")
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[key for key in rows[0] if not key.startswith("_")],
        )
        writer.writeheader()
        writer.writerows(
            {key: value for key, value in row.items() if not key.startswith("_")}
            for row in rows
        )


def value_for_metric(
    metrics: list[dict[str, Any]],
    metric_name: str,
    key: str,
) -> float | None:
    row = next(item for item in metrics if item["metric"] == metric_name)
    return row[key]


def comparison_figure(
    path: Path,
    title: str,
    ylabel: str,
    baseline: float | None,
    procura: float | None,
    labels: tuple[str, str] = ("Price-Only Baseline", "Procura AI"),
    ylim: tuple[float, float] | None = None,
    percent: bool = False,
) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.5), layout="constrained")
    positions = []
    values = []
    colors = []
    for index, value in enumerate((baseline, procura)):
        if value is not None:
            positions.append(index)
            values.append(value)
            colors.append("#5b6b8a" if index == 0 else "#168f83")
    bars = ax.bar(positions, values, color=colors, width=0.58)
    ax.set_xticks([0, 1], labels)
    ax.set_title(title, loc="left", fontweight="bold", pad=14)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Supplier selection approach")
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    if ylim:
        ax.set_ylim(*ylim)
    for bar, value in zip(bars, values):
        label = f"{value:.2f}%" if percent else f"{value:.6f}"
        ax.annotate(
            label,
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )
    if baseline is None:
        ax.text(
            0.02,
            0.95,
            "Price-only baseline: N/A (no workflow)",
            transform=ax.transAxes,
            va="top",
            fontsize=9,
            color="#4b5563",
        )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def generate_figures(
    metrics: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    metric_names = {row["metric"]: row for row in metrics}
    plots = [
        ("Selection Accuracy (%)", "Supplier Selection Accuracy", "Accuracy (%)",
         "accuracy_comparison.png", (0, 100), True),
        ("Ranking Performance (mean Spearman rho)", "Ranking Performance",
         "Mean Spearman's rho", "ranking_comparison.png", (-1, 1), False),
        ("Budget Compliance (%)", "Budget Compliance", "Compliance (%)",
         "budget_compliance.png", (0, 100), True),
        ("Evidence Coverage (%)", "Evidence Coverage", "Offer records covered (%)",
         "evidence_coverage.png", (0, 100), True),
        ("Workflow Success Rate (%)", "Workflow Success Rate",
         "Successful applicable workflows (%)", "workflow_success.png",
         (0, 100), True),
        ("Average Processing Time (seconds; lower is better)",
         "Average Processing Time (lower is better)", "Seconds per case",
         "processing_time.png", None, False),
    ]
    for metric_name, title, ylabel, filename, ylim, percent in plots:
        row = metric_names[metric_name]
        comparison_figure(
            FIGURES_DIR / filename,
            title,
            ylabel,
            row["_baseline_value"],
            row["_procura_value"],
            ylim=ylim,
            percent=percent,
        )

    percentage_names = [
        "Selection Accuracy (%)",
        "Budget Compliance (%)",
        "Evidence Coverage (%)",
    ]
    positions = list(range(len(percentage_names)))
    width = 0.34
    fig, ax = plt.subplots(figsize=(9.2, 5.0), layout="constrained")
    baseline_values = [metric_names[name]["_baseline_value"] for name in percentage_names]
    procura_values = [metric_names[name]["_procura_value"] for name in percentage_names]
    baseline_bars = ax.bar(
        [position - width / 2 for position in positions],
        baseline_values,
        width,
        label="Price-Only Baseline",
        color="#5b6b8a",
    )
    procura_bars = ax.bar(
        [position + width / 2 for position in positions],
        procura_values,
        width,
        label="Procura AI",
        color="#168f83",
    )
    ax.set_title("Overall Comparable Percentage Metrics", loc="left", fontweight="bold")
    ax.set_ylabel("Percentage (%)")
    ax.set_xlabel("Metric")
    ax.set_xticks(
        positions,
        ["Selection accuracy", "Budget compliance", "Evidence coverage"],
    )
    ax.set_ylim(0, 108)
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    for bars in (baseline_bars, procura_bars):
        for bar in bars:
            ax.annotate(
                f"{bar.get_height():.1f}%",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )
    fig.savefig(FIGURES_DIR / "overall_metrics.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    eligible = [
        row for row in case_results
        if row["expected_supplier_id"]
    ]
    positions = list(range(len(eligible)))
    fig, ax = plt.subplots(figsize=(11, 5.0), layout="constrained")
    ax.bar(
        [position - width / 2 for position in positions],
        [100 if row["baseline_correct"] else 0 for row in eligible],
        width,
        label="Price-Only Baseline",
        color="#5b6b8a",
    )
    ax.bar(
        [position + width / 2 for position in positions],
        [100 if row["procura_correct"] else 0 for row in eligible],
        width,
        label="Procura AI",
        color="#168f83",
    )
    ax.set_title("Case-Level Supplier Selection vs. Reference", loc="left", fontweight="bold")
    ax.set_ylabel("Reference selection match (%)")
    ax.set_xlabel("Benchmark case")
    ax.set_xticks(positions, [row["case_id"] for row in eligible], rotation=45)
    ax.set_yticks([0, 100], ["Incorrect", "Correct"])
    ax.set_ylim(-10, 115)
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    fig.savefig(FIGURES_DIR / "case_level_selection.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def failure_analysis(
    cases_by_id: dict[str, dict[str, Any]],
    offers_by_case: dict[str, list[dict[str, Any]]],
    candidates_by_case: dict[str, list[dict[str, Any]]],
    workflows: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    def candidates(case_id: str) -> set[str]:
        return {
            offer["supplier_id"]
            for offer in candidates_by_case[case_id]
        }

    rows: list[dict[str, str]] = []
    missing_price = [
        offer for offer in offers_by_case["C09"]
        if offer["unit_price"] is None
    ]
    missing_price_pass = bool(missing_price) and all(
        offer["supplier_id"] not in candidates("C09")
        for offer in missing_price
    )
    rows.append({
        "scenario": "Missing price",
        "expected_behavior": "An internal offer with no stored price is excluded by sourcing.",
        "baseline_behavior": (
            "Receives the same source-filtered candidates; missing-price offer absent."
        ),
        "procura_behavior": (
            "find_internal_supplier_offers excludes the missing-price row before scoring."
        ),
        "pass_fail": "PASS" if missing_price_pass else "FAIL",
    })

    missing_evidence = next(
        offer for offer in offers_by_case["C10"]
        if not offer["source_evidence"] or not offer["price_evidence"]
    )
    evidence_pass = missing_evidence["supplier_id"] in candidates("C10")
    rows.append({
        "scenario": "Missing source/price evidence",
        "expected_behavior": (
            "The evidence gap is reflected in coverage; internal sourcing may still "
            "return a priced row because it does not validate evidence fields."
        ),
        "baseline_behavior": "Receives the shared candidate; evidence is not a ranking input.",
        "procura_behavior": (
            "Scores the returned row; no evidence validation is implemented for "
            "internal catalog offers."
        ),
        "pass_fail": "PASS" if evidence_pass else "FAIL",
    })

    invalid = next(
        offer for offer in offers_by_case["C11"]
        if not offer["supplier_name"].strip()
        or not 0 <= offer["reliability_score"] <= 1
    )
    invalid_retained = invalid["supplier_id"] in candidates("C11")
    rows.append({
        "scenario": "Invalid supplier information",
        "expected_behavior": "Reject an offer with a blank supplier name or out-of-range reliability.",
        "baseline_behavior": (
            "Uses the source-filtered offer set and does not validate supplier identity."
        ),
        "procura_behavior": (
            "Current internal sourcing retains the invalid record; scoring does not "
            "validate supplier identity."
        ),
        "pass_fail": "FAIL" if invalid_retained else "PASS",
    })

    no_offer = not candidates("C12")
    rows.append({
        "scenario": "No valid supplier offer",
        "expected_behavior": "Finish sourcing as NO_MATCHING_OFFERS without creating a quote or approval.",
        "baseline_behavior": "No supplier is selected from the empty candidate set.",
        "procura_behavior": (
            f"Workflow status={workflows['C12']['status_after_resume']}; "
            f"quotes={workflows['C12']['quote_count']}; "
            f"approvals={workflows['C12']['approval_count']}; "
            f"approval interrupt={workflows['C12']['paused_for_approval']}."
        ),
        "pass_fail": (
            "PASS"
            if no_offer
            and workflows["C12"]["status_after_resume"] == "NO_MATCHING_OFFERS"
            and not workflows["C12"]["paused_for_approval"]
            and workflows["C12"]["quote_count"] == 0
            and workflows["C12"]["approval_count"] == 0
            else "FAIL"
        ),
    })

    over_budget = [
        offer for offer in offers_by_case["C07"]
        if offer["unit_price"] is not None
        and offer["unit_price"] * cases_by_id["C07"]["quantity"]
        > cases_by_id["C07"]["budget"]
    ]
    budget_pass = bool(over_budget) and all(
        offer["supplier_id"] not in candidates("C07")
        for offer in over_budget
    )
    rows.append({
        "scenario": "Budget violation",
        "expected_behavior": "Offers exceeding budget are excluded before either selector runs.",
        "baseline_behavior": "Uses only shared source-filtered offers; selected offer is within budget.",
        "procura_behavior": "Internal sourcing enforces total price <= budget before scoring.",
        "pass_fail": "PASS" if budget_pass else "FAIL",
    })

    rejected = workflows["C13"]
    rows.append({
        "scenario": "Approval rejection",
        "expected_behavior": "Record rejection and do not create a purchase order.",
        "baseline_behavior": "N/A; price-only ranking has no approval workflow.",
        "procura_behavior": (
            f"Decision={rejected['approval_decision']}; "
            f"status={rejected['status_after_resume']}; "
            f"purchase orders={rejected['purchase_order_count']}."
        ),
        "pass_fail": (
            "PASS"
            if rejected["status_after_resume"] == "REJECTED"
            and rejected["purchase_order_count"] == 0
            else "FAIL"
        ),
    })

    resumed = workflows["C15"]
    rows.append({
        "scenario": "Workflow interruption/resumption",
        "expected_behavior": "Pause at human approval, resume with decision, and reach delivery state.",
        "baseline_behavior": "N/A; price-only ranking has no workflow state.",
        "procura_behavior": (
            f"paused={resumed['paused_for_approval']}; resumed={resumed['resumed']}; "
            f"final status={resumed['status_after_resume']}."
        ),
        "pass_fail": (
            "PASS"
            if resumed["paused_for_approval"]
            and resumed["resumed"]
            and resumed["status_after_resume"] == "DELIVERY_IN_PROGRESS"
            else "FAIL"
        ),
    })
    return rows


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def format_metric(value: str, unit: str = "") -> str:
    if value == "N/A":
        return value
    number = float(value)
    if unit == "%":
        return f"{number:.2f}%"
    if unit == "s":
        return f"{number:.9f} s"
    return f"{number:.6f}"


def build_report(
    cases: list[dict[str, Any]],
    offers_by_case: dict[str, list[dict[str, Any]]],
    candidates_by_case: dict[str, list[dict[str, Any]]],
    case_results: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    summary: dict[str, Any],
    failures: list[dict[str, str]],
    elapsed_s: float,
) -> str:
    metric_rows = []
    units = {
        "Selection Accuracy (%)": "%",
        "Budget Compliance (%)": "%",
        "Evidence Coverage (%)": "%",
        "Workflow Success Rate (%)": "%",
        "Average Processing Time (seconds; lower is better)": "s",
    }
    for metric in metrics:
        unit = units.get(metric["metric"], "")
        metric_rows.append([
            metric["metric"],
            format_metric(metric["price_only_baseline"], unit),
            format_metric(metric["procura_ai"], unit),
            format_metric(metric["difference_procura_minus_baseline"], unit),
            format_metric(metric["improvement_percent"], "%"),
        ])
    selection_accuracy = next(
        metric for metric in metrics if metric["metric"] == "Selection Accuracy (%)"
    )
    ranking = next(
        metric for metric in metrics
        if metric["metric"] == "Ranking Performance (mean Spearman rho)"
    )
    budget = next(metric for metric in metrics if metric["metric"] == "Budget Compliance (%)")
    evidence = next(metric for metric in metrics if metric["metric"] == "Evidence Coverage (%)")
    workflow = next(metric for metric in metrics if metric["metric"] == "Workflow Success Rate (%)")
    processing = next(
        metric for metric in metrics
        if metric["metric"] == "Average Processing Time (seconds; lower is better)"
    )
    scenario_rows = [
        [
            row["scenario"],
            row["expected_behavior"],
            row["baseline_behavior"],
            row["procura_behavior"],
            row["pass_fail"],
        ]
        for row in failures
    ]
    dataset_count = sum(len(items) for items in offers_by_case.values())
    eligible_case_count = sum(bool(candidates_by_case[case["case_id"]]) for case in cases)

    return f"""# Procura AI Supplier-Selection Evaluation

## 1. Experimental Objective

Compare the implemented deterministic Procura AI supplier-ranking approach with a separate **Price-Only Baseline** on the same 20-case synthetic benchmark. The experiment evaluates selection and ranking against a predeclared independent procurement reference rubric and exercises the existing approval interrupt/resume workflow. It does not alter Procura's scoring logic or use live supplier data.

## 2. Algorithms Compared

**A. Price-Only Baseline (evaluation-only):** receives the same source-filtered offers as Procura; sorts by total price ascending, then supplier name case-insensitively and supplier ID for deterministic exact-price ties.

**B. Procura AI Multi-Criteria Supplier Evaluation (existing code):** calls `find_internal_supplier_offers` and then the unchanged `evaluate_supplier_offers` in `app/services/quote_agent.py`. For each returned offer, the current implementation calculates:

```text
price_score       = max(0, 60 * (1 - total_price / budget))
reliability_score = max(0, min(25, reliability_score * 25))
verified_score    = 10 if verification_status.upper() == "VERIFIED" else 0
lead_score        = max(0, 15 * (1 - min(lead_time_days, 60) / 60))
                   if lead_time_days is truthy, otherwise 0
evaluation_score  = round(price_score + reliability_score
                           + verified_score + lead_score, 2)
```

It sorts by evaluation score descending and total price ascending. If both are equal, Python's stable sort retains the input order; the scoring function has no explicit final supplier-name tie-break. The internal source helper orders by total price and lead time before the scoring sort. The scoring function itself does not filter over-budget offers; the internal source helper filters missing prices, currency mismatches, and total prices above budget before the scorer is called. The 60/25/10/15 component caps total 110 points, despite the surrounding workflow displaying scores as `/100`.

The external Tavily path and explicit-price parser were inspected but not exercised against the live web in this evaluation. They are outside this internal-catalog benchmark.

## 3. Dataset

`benchmark_dataset.csv` is a **SYNTHETIC BENCHMARK DATASET**, authored for this evaluation because repository test fixtures contain only a small number of workflow examples and are not a comparative dataset. It contains {len(cases)} procurement cases and {dataset_count} supplier-offer rows. Cases have multiple offer records and cover price, reliability, verification, lead time, budget, missing values, currency, evidence, approval, and workflow scenarios.

The data is not actual Procura user data, supplier quotations, or market research. `source_evidence` and `price_evidence` are synthetic labels/placeholders, not external citations or verified documents. Internal supplier-product persistence supports price, currency, lead time, and source, but has no dedicated evidence field; evidence coverage therefore measures the completeness of the synthetic input fields and must not be interpreted as live citation quality.

## 4. Ground Truth / Reference Selection

The independent reference is a predeclared lexicographic procurement rubric, not the output of either evaluated algorithm:

1. Supplier identity is acceptable before missing/invalid identity (nonblank supplier name and reliability within `[0, 1]`).
2. Verified suppliers before unverified suppliers.
3. Higher reliability score.
4. Shorter known lead time (missing lead time last).
5. Lower total price.
6. Supplier name and supplier ID as deterministic final ties.

Reference selection is the first supplier in that order. This transparent policy reflects risk control, supplier trust, delivery, and then cost; it is intentionally not Procura's weighted formula. Both algorithms rank the exact same candidate set produced by the actual internal sourcing/filtering helper. This means the implementation's failure to exclude invalid supplier identity is visible rather than silently repaired in the benchmark.

## 5. Experimental Setup

The benchmark seeded an isolated in-memory SQLite database from the CSV and invoked the real `find_internal_supplier_offers` query/filter and `evaluate_supplier_offers` scorer. The baseline is a separate function in `run_evaluation.py`. Both used the same per-case budget, currency, and offers. Workflow cases invoked the actual LangGraph with its deterministic demo LLM adapter, an in-memory checkpointer, and the benchmark's already-filtered synthetic internal offers. No OpenRouter or Tavily network call was made. Cases with offers reached the actual human approval interrupt and were resumed using the predeclared CSV decision; the rejection case was checked for absence of a PO.

There were {eligible_case_count} cases with at least one source-filtered candidate. Total evaluation runtime (including workflow execution, metrics, figures, and output preparation) was {elapsed_s:.6f} seconds. Selector processing times below include the source helper query/filter plus the relevant selection/ranking call, measured with `time.perf_counter`; they exclude database seeding and the separate workflow.

Reproduce from the repository root with `python evaluation/run_evaluation.py` after installing `requirements.txt`.

## 6. Evaluation Metrics

- **Selection accuracy:** matching selected supplier / cases with at least one eligible offer. No-offer cases are not accuracy-eligible.
- **Ranking:** mean per-case Spearman rank correlation (`rho`) between each algorithm's complete ordering and the reference ordering, for cases with at least two eligible offers. The case-level CSV records each rho and complete ranking.
- **Budget compliance:** selected suppliers within budget / cases with a selected supplier. The actual internal source helper filters offers above budget for both algorithms.
- **Evidence coverage:** raw offer rows with positive explicit price and nonblank source-evidence and price-evidence fields / all raw offer rows, including rows rejected by sourcing. It is a shared-input property, so values are identical for both algorithms.
- **Workflow success:** eligible cases whose actual graph paused at approval, resumed, and reached the expected post-decision terminal state / eligible workflow cases. Rejection is a successful, correctly completed human decision; it must not generate a PO. The baseline has no workflow, so its value is N/A.
- **Processing time:** measured wall-clock seconds per case; lower is better. Total and average are sums/means of those per-case measurements.

## 7. Accuracy Results

Price-Only Baseline: {summary['baseline_correct']}/{summary['accuracy_case_count']} = {selection_accuracy['price_only_baseline']}%. Procura AI: {summary['procura_correct']}/{summary['accuracy_case_count']} = {selection_accuracy['procura_ai']}%. Accuracy is measured against the independent rubric above, not user outcomes or real procurement savings.

## 8. Ranking Results

Mean Spearman rho was {ranking['price_only_baseline']} for the baseline and {ranking['procura_ai']} for Procura, across {summary['ranking_case_count']} multi-offer cases. The rho values are descriptive benchmark results only.

## 9. Budget Compliance Results

Baseline: {budget['price_only_baseline']}%; Procura AI: {budget['procura_ai']}%. The actual internal source path excludes offers above budget before either ranking function runs; budget compliance is therefore expected to be equal on this benchmark.

## 10. Evidence Coverage Results

Both algorithms: {evidence['procura_ai']}% ({summary['evidence_covered_offers']}/{summary['evidence_offer_count']} synthetic raw offer rows). Evidence fields are not ranking inputs. Because the current internal-offer schema does not store an evidence snippet, this is benchmark input-field coverage, not a measured production evidence-retention rate.

## 11. Workflow Success Results

Procura AI: {workflow['procura_ai']}% ({summary['workflow_successes']}/{summary['workflow_applicable_cases']}) of applicable cases. Price-only baseline: N/A. Approval rejection was included as a valid completed workflow decision only when the graph reached `REJECTED` and created no purchase order. Cases with no valid offers are outside the workflow-success denominator and are separately analyzed.

## 12. Processing Time Results

- Price-Only Baseline: total={summary['baseline_total_processing_s']:.9f}s; average={processing['price_only_baseline']}s per case.
- Procura AI: total={summary['procura_total_processing_s']:.9f}s; average={processing['procura_ai']}s per case.
- Baseline distribution: {time_summary(summary['baseline_times'])}.
- Procura distribution: {time_summary(summary['procura_times'])}.
- End-to-end workflow distribution (eligible cases): {time_summary(summary['workflow_times'])}.

These measurements are local single-run timings on a synthetic in-memory SQLite benchmark, not a statistically controlled performance study. The dataset is small and designed rather than randomly sampled; no significance test or population-level inference is warranted.

## 13. Failure Analysis

{markdown_table(['Scenario', 'Expected behavior', 'Baseline behavior', 'Procura behavior', 'Pass/Fail'], scenario_rows)}

The invalid-supplier-information scenario is intentionally reported as a failure if the actual source helper retains it. This reveals a validation limitation; no fix was made because the requested scope was evaluation, not architecture or scoring changes.

## 14. Baseline vs Procura AI Comparison

{markdown_table(['Metric', 'Price-Only Baseline', 'Procura AI', 'Difference (Procura - baseline)', 'Improvement %'], metric_rows)}

The improvement column is N/A where a relative improvement is not meaningful (including shared evidence coverage, workflow N/A, zero/undefined baseline, and rank correlation). For processing time, improvement is a relative reduction in elapsed time; a negative value means Procura took longer.

## 15. Limitations

- The benchmark is synthetic and not representative of a statistically sampled supplier population.
- The reference rubric is a transparent policy choice, not adjudicated procurement ground truth; a different policy could change accuracy and rankings.
- The experiment covers internal catalog filtering and scoring. It does not measure live Tavily result quality, external supplier verification, OpenRouter quality, RFQ response, realized savings, or actual supplier performance.
- Supplier evidence is synthetic input metadata and is not stored as a first-class evidence object in the internal offer model.
- The implemented reliability multiplier assumes a 0-to-1 score; the current code clamps the product but does not validate the input range or supplier identity.
- The `60/25/10/15` score component caps sum to 110, not 100.
- Exact Procura ties on both score and total price retain input order rather than using a documented explicit tie-break.
- Timing is environment-specific and one-run only; it does not establish statistically significant speed differences.

## 16. Final Findings

On this synthetic benchmark, **{('Procura AI' if summary['procura_correct'] > summary['baseline_correct'] else 'Price-Only Baseline' if summary['baseline_correct'] > summary['procura_correct'] else 'both approaches equally')}** matched the independent reference for more cases. Mean ranking correlations were {ranking['price_only_baseline']} (baseline) and {ranking['procura_ai']} (Procura). Both algorithms had {budget['procura_ai']}% budget compliance because they share the existing budget filter. Evidence coverage was {evidence['procura_ai']}% for the common synthetic input. Procura's actual workflow success was {workflow['procura_ai']}%; the baseline has no workflow equivalent. Average measured selector time was {processing['price_only_baseline']}s (baseline) and {processing['procura_ai']}s (Procura). These findings apply only to this synthetic run and do not demonstrate production accuracy, real-world procurement improvement, or statistical significance.

## Generated Artifacts

- `results/case_level_results.csv`
- `results/metrics_comparison.csv`
- `results/failure_analysis.csv`
- `figures/accuracy_comparison.png`
- `figures/ranking_comparison.png`
- `figures/budget_compliance.png`
- `figures/evidence_coverage.png`
- `figures/workflow_success.png`
- `figures/processing_time.png`
- `figures/overall_metrics.png`
- `figures/case_level_selection.png`
"""


def verify_generated_outputs(
    metrics: list[dict[str, Any]],
    offers_by_case: dict[str, list[dict[str, Any]]],
) -> None:
    with (RESULTS_DIR / "case_level_results.csv").open(
        newline="",
        encoding="utf-8",
    ) as input_file:
        cases = list(csv.DictReader(input_file))
    with (RESULTS_DIR / "metrics_comparison.csv").open(
        newline="",
        encoding="utf-8",
    ) as input_file:
        metric_file_rows = {
            row["metric"]: row for row in csv.DictReader(input_file)
        }
    report = (EVALUATION_DIR / "evaluation_report.md").read_text(encoding="utf-8")

    eligible_for_accuracy = [
        row for row in cases if row["expected_supplier_id"]
    ]
    baseline_selected = [
        row for row in cases if row["baseline_selected_supplier"] != "NONE"
    ]
    procura_selected = [
        row for row in cases if row["procura_selected_supplier"] != "NONE"
    ]
    eligible_for_ranking = [
        row for row in cases if row["baseline_spearman_rho"]
    ]
    applicable_workflows = [
        row for row in cases if row["workflow_applicable"] == "True"
    ]
    evidence_coverage, _, _ = raw_evidence_coverage(offers_by_case)

    expected: dict[str, tuple[float | None, float | None]] = {
        "Selection Accuracy (%)": (
            100 * sum(row["baseline_correct"] == "True" for row in eligible_for_accuracy)
            / len(eligible_for_accuracy),
            100 * sum(row["procura_correct"] == "True" for row in eligible_for_accuracy)
            / len(eligible_for_accuracy),
        ),
        "Ranking Performance (mean Spearman rho)": (
            statistics.mean(float(row["baseline_spearman_rho"]) for row in eligible_for_ranking),
            statistics.mean(float(row["procura_spearman_rho"]) for row in eligible_for_ranking),
        ),
        "Budget Compliance (%)": (
            100 * sum(row["baseline_budget_compliant"] == "True" for row in baseline_selected)
            / len(baseline_selected),
            100 * sum(row["procura_budget_compliant"] == "True" for row in procura_selected)
            / len(procura_selected),
        ),
        "Evidence Coverage (%)": (evidence_coverage, evidence_coverage),
        "Workflow Success Rate (%)": (
            None,
            100 * sum(row["workflow_success"] == "True" for row in applicable_workflows)
            / len(applicable_workflows),
        ),
        "Average Processing Time (seconds; lower is better)": (
            statistics.mean(float(row["processing_time_baseline_s"]) for row in cases),
            statistics.mean(float(row["processing_time_procura_s"]) for row in cases),
        ),
    }
    for name, (baseline, procura) in expected.items():
        stored = metric_file_rows[name]
        for column, expected_value in (
            ("price_only_baseline", baseline),
            ("procura_ai", procura),
        ):
            if expected_value is None:
                if stored[column] != "N/A":
                    raise AssertionError(f"{name} {column} should be N/A.")
                continue
            if not math.isclose(
                float(stored[column]),
                expected_value,
                rel_tol=0,
                abs_tol=1e-6,
            ):
                raise AssertionError(
                    f"{name} {column} does not match raw case-level CSV data."
                )
            if f"{expected_value:.6f}" not in report:
                raise AssertionError(f"{name} value is missing from report.")
    if len(cases) != 20:
        raise AssertionError(f"Expected 20 case-level rows; found {len(cases)}.")
    if len(metrics) != len(expected):
        raise AssertionError("The figure/report metric set changed unexpectedly.")


def main() -> None:
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_started = time.perf_counter()
    cases, offers_by_case = read_dataset()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        Base.metadata.create_all(engine)
        seed_database(Session, cases, offers_by_case)
        candidates_by_case = {
            case["case_id"]: source_candidates(Session, case)
            for case in cases
        }
        workflows = run_workflows(Session, cases, candidates_by_case)
        case_results, baseline_times, procura_times, baseline_rhos, procura_rhos = (
            build_case_results(
                Session,
                cases,
                offers_by_case,
                candidates_by_case,
                workflows,
            )
        )
        metrics, summary = calculate_metrics(
            case_results,
            offers_by_case,
            workflows,
            baseline_times,
            procura_times,
            baseline_rhos,
            procura_rhos,
        )
        failures = failure_analysis(
            {case["case_id"]: case for case in cases},
            offers_by_case,
            candidates_by_case,
            workflows,
        )
        write_csv(RESULTS_DIR / "case_level_results.csv", case_results)
        write_csv(RESULTS_DIR / "metrics_comparison.csv", metrics)
        write_csv(RESULTS_DIR / "failure_analysis.csv", failures)
        generate_figures(metrics, case_results)

        # Verify common candidates, budget compliance, and generated output shapes.
        for row in case_results:
            if row["eligible_offer_count"]:
                if row["baseline_budget_compliant"] is not True:
                    raise AssertionError(f"Baseline violated budget in {row['case_id']}.")
                if row["procura_budget_compliant"] is not True:
                    raise AssertionError(f"Procura violated budget in {row['case_id']}.")
            elif (
                row["baseline_selected_supplier"] != "NONE"
                or row["procura_selected_supplier"] != "NONE"
            ):
                raise AssertionError(f"Selected supplier without candidates in {row['case_id']}.")
        for filename in (
            "case_level_results.csv",
            "metrics_comparison.csv",
            "failure_analysis.csv",
        ):
            if not (RESULTS_DIR / filename).is_file():
                raise AssertionError(f"Missing generated result: {filename}")
        for filename in (
            "accuracy_comparison.png",
            "ranking_comparison.png",
            "budget_compliance.png",
            "evidence_coverage.png",
            "workflow_success.png",
            "processing_time.png",
            "overall_metrics.png",
            "case_level_selection.png",
        ):
            image_path = FIGURES_DIR / filename
            if not image_path.is_file() or image_path.stat().st_size == 0:
                raise AssertionError(f"Missing or empty figure: {filename}")
        elapsed_s = time.perf_counter() - run_started
        report = build_report(
            cases,
            offers_by_case,
            candidates_by_case,
            case_results,
            metrics,
            summary,
            failures,
            elapsed_s,
        )
        (EVALUATION_DIR / "evaluation_report.md").write_text(
            report,
            encoding="utf-8",
        )
        verify_generated_outputs(metrics, offers_by_case)
        print(f"Benchmark cases: {len(cases)}")
        print(f"Raw offer rows: {sum(map(len, offers_by_case.values()))}")
        print(f"Eligible workflow cases: {summary['workflow_applicable_cases']}")
        print(f"Evaluation runtime: {elapsed_s:.6f} seconds")
        for metric in metrics:
            print(
                f"{metric['metric']}: baseline={metric['price_only_baseline']}, "
                f"procura={metric['procura_ai']}, "
                f"difference={metric['difference_procura_minus_baseline']}"
            )
        print("Generated evaluation results, report, and figures successfully.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
