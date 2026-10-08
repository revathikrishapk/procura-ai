# Procura AI Supplier-Selection Evaluation

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

`benchmark_dataset.csv` is a **SYNTHETIC BENCHMARK DATASET**, authored for this evaluation because repository test fixtures contain only a small number of workflow examples and are not a comparative dataset. It contains 20 procurement cases and 60 supplier-offer rows. Cases have multiple offer records and cover price, reliability, verification, lead time, budget, missing values, currency, evidence, approval, and workflow scenarios.

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

There were 19 cases with at least one source-filtered candidate. Total evaluation runtime (including workflow execution, metrics, figures, and output preparation) was 15.558566 seconds. Selector processing times below include the source helper query/filter plus the relevant selection/ranking call, measured with `time.perf_counter`; they exclude database seeding and the separate workflow.

Reproduce from the repository root with `python evaluation/run_evaluation.py` after installing `requirements.txt`.

## 6. Evaluation Metrics

- **Selection accuracy:** matching selected supplier / cases with at least one eligible offer. No-offer cases are not accuracy-eligible.
- **Ranking:** mean per-case Spearman rank correlation (`rho`) between each algorithm's complete ordering and the reference ordering, for cases with at least two eligible offers. The case-level CSV records each rho and complete ranking.
- **Budget compliance:** selected suppliers within budget / cases with a selected supplier. The actual internal source helper filters offers above budget for both algorithms.
- **Evidence coverage:** raw offer rows with positive explicit price and nonblank source-evidence and price-evidence fields / all raw offer rows, including rows rejected by sourcing. It is a shared-input property, so values are identical for both algorithms.
- **Workflow success:** eligible cases whose actual graph paused at approval, resumed, and reached the expected post-decision terminal state / eligible workflow cases. Rejection is a successful, correctly completed human decision; it must not generate a PO. The baseline has no workflow, so its value is N/A.
- **Processing time:** measured wall-clock seconds per case; lower is better. Total and average are sums/means of those per-case measurements.

## 7. Accuracy Results

Price-Only Baseline: 2/19 = 10.526316%. Procura AI: 5/19 = 26.315789%. Accuracy is measured against the independent rubric above, not user outcomes or real procurement savings.

## 8. Ranking Results

Mean Spearman rho was -0.694444 for the baseline and -0.111111 for Procura, across 18 multi-offer cases. The rho values are descriptive benchmark results only.

## 9. Budget Compliance Results

Baseline: 100.000000%; Procura AI: 100.000000%. The actual internal source path excludes offers above budget before either ranking function runs; budget compliance is therefore expected to be equal on this benchmark.

## 10. Evidence Coverage Results

Both algorithms: 93.333333% (56/60 synthetic raw offer rows). Evidence fields are not ranking inputs. Because the current internal-offer schema does not store an evidence snippet, this is benchmark input-field coverage, not a measured production evidence-retention rate.

## 11. Workflow Success Results

Procura AI: 100.000000% (19/19) of applicable cases. Price-only baseline: N/A. Approval rejection was included as a valid completed workflow decision only when the graph reached `REJECTED` and created no purchase order. Cases with no valid offers are outside the workflow-success denominator and are separately analyzed.

## 12. Processing Time Results

- Price-Only Baseline: total=0.182945100s; average=0.009147s per case.
- Procura AI: total=0.247491600s; average=0.012375s per case.
- Baseline distribution: mean=0.009147255s; median=0.007897200s; sample SD=0.006304865s; min=0.001720600s; max=0.018944400s; n=20.
- Procura distribution: mean=0.012374580s; median=0.013708350s; sample SD=0.006713634s; min=0.001595600s; max=0.029748600s; n=20.
- End-to-end workflow distribution (eligible cases): mean=0.230403068s; median=0.203292600s; sample SD=0.128857533s; min=0.082896200s; max=0.676447500s; n=19.

These measurements are local single-run timings on a synthetic in-memory SQLite benchmark, not a statistically controlled performance study. The dataset is small and designed rather than randomly sampled; no significance test or population-level inference is warranted.

## 13. Failure Analysis

| Scenario | Expected behavior | Baseline behavior | Procura behavior | Pass/Fail |
| --- | --- | --- | --- | --- |
| Missing price | An internal offer with no stored price is excluded by sourcing. | Receives the same source-filtered candidates; missing-price offer absent. | find_internal_supplier_offers excludes the missing-price row before scoring. | PASS |
| Missing source/price evidence | The evidence gap is reflected in coverage; internal sourcing may still return a priced row because it does not validate evidence fields. | Receives the shared candidate; evidence is not a ranking input. | Scores the returned row; no evidence validation is implemented for internal catalog offers. | PASS |
| Invalid supplier information | Reject an offer with a blank supplier name or out-of-range reliability. | Uses the source-filtered offer set and does not validate supplier identity. | Current internal sourcing retains the invalid record; scoring does not validate supplier identity. | FAIL |
| No valid supplier offer | Finish sourcing as NO_MATCHING_OFFERS without creating a quote or approval. | No supplier is selected from the empty candidate set. | Workflow status=NO_MATCHING_OFFERS; quotes=0; approvals=0; approval interrupt=False. | PASS |
| Budget violation | Offers exceeding budget are excluded before either selector runs. | Uses only shared source-filtered offers; selected offer is within budget. | Internal sourcing enforces total price <= budget before scoring. | PASS |
| Approval rejection | Record rejection and do not create a purchase order. | N/A; price-only ranking has no approval workflow. | Decision=reject; status=REJECTED; purchase orders=0. | PASS |
| Workflow interruption/resumption | Pause at human approval, resume with decision, and reach delivery state. | N/A; price-only ranking has no workflow state. | paused=True; resumed=True; final status=DELIVERY_IN_PROGRESS. | PASS |

The invalid-supplier-information scenario is intentionally reported as a failure if the actual source helper retains it. This reveals a validation limitation; no fix was made because the requested scope was evaluation, not architecture or scoring changes.

## 14. Baseline vs Procura AI Comparison

| Metric | Price-Only Baseline | Procura AI | Difference (Procura - baseline) | Improvement % |
| --- | --- | --- | --- | --- |
| Selection Accuracy (%) | 10.53% | 26.32% | 15.79% | 150.00% |
| Ranking Performance (mean Spearman rho) | -0.694444 | -0.111111 | 0.583333 | N/A |
| Budget Compliance (%) | 100.00% | 100.00% | 0.00% | 0.00% |
| Evidence Coverage (%) | 93.33% | 93.33% | 0.00% | N/A |
| Workflow Success Rate (%) | N/A | 100.00% | N/A | N/A |
| Average Processing Time (seconds; lower is better) | 0.009147000 s | 0.012375000 s | 0.003227000 s | -35.28% |

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

On this synthetic benchmark, **Procura AI** matched the independent reference for more cases. Mean ranking correlations were -0.694444 (baseline) and -0.111111 (Procura). Both algorithms had 100.000000% budget compliance because they share the existing budget filter. Evidence coverage was 93.333333% for the common synthetic input. Procura's actual workflow success was 100.000000%; the baseline has no workflow equivalent. Average measured selector time was 0.009147s (baseline) and 0.012375s (Procura). These findings apply only to this synthetic run and do not demonstrate production accuracy, real-world procurement improvement, or statistical significance.

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
