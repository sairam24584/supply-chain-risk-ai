"""DeepEval evaluation harness for the multi-agent assistant.

Runs the live LangGraph pipeline over `GOLDEN_CASES` and scores each output with:
  * FaithfulnessMetric         — answer must be grounded in retrieved context
  * AnswerRelevancyMetric      — answer must address the query
  * GEval (custom rubric)      — mitigation quality (LLM-as-judge)

Results are written to data/eval_results.json and can be fetched via GET /api/eval/results.

Usage (from backend/):
    python -m scripts.eval                # full run
    python -m scripts.eval --quick        # only first 2 cases
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.graph import get_graph  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import logger, setup_logging  # noqa: E402
from scripts.eval_golden import GOLDEN_CASES, GoldenCase  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parents[2] / "data" / "eval_results.json"


def _format_context(hits: list[dict]) -> list[str]:
    """DeepEval's `LLMTestCase.retrieval_context` expects a list of strings."""
    return [h.get("text", "") for h in hits[:8]]


def _run_one(case: GoldenCase):
    from deepeval.test_case import LLMTestCase

    graph = get_graph()
    state = graph.invoke({"query": case.query, "top_k": 8})
    answer = state.get("recommendation", "") or ""
    plan = state.get("recommendation_plan")
    if plan and not answer:
        summary = plan.get("executive_summary", "")
        actions = plan.get("actions", [])
        action_lines = "\n".join(
            f"- {a.get('title')} (owner: {a.get('owner_role')}, {a.get('timeframe_days')}d)"
            for a in (actions or [])
        )
        answer = f"{summary}\n{action_lines}".strip()
    hits = state.get("retrieved_hits", [])

    return LLMTestCase(
        input=case.query,
        actual_output=answer or "(no answer)",
        retrieval_context=_format_context(hits),
        expected_output="; ".join(case.expected_concepts),
    )


def _build_metrics(model_name: str = "gpt-4o-mini"):
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCaseParams

    mitigation_rubric = GEval(
        name="Mitigation Quality",
        criteria=(
            "Determine whether the recommendation is (1) actionable with owner+timeframe, "
            "(2) grounded in the retrieved context (no invented suppliers/SKUs), "
            "(3) prioritised, and (4) includes a justifiable overall risk score."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        threshold=0.7,
        model=model_name,
    )

    return [
        FaithfulnessMetric(threshold=0.7, model=model_name),
        AnswerRelevancyMetric(threshold=0.7, model=model_name),
        mitigation_rubric,
    ]


def _save_results(case_results: list[dict], metrics_summary: dict) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "num_cases": len(case_results),
        "metrics_summary": metrics_summary,
        "cases": case_results,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2))
    logger.info("Eval results saved to {}", RESULTS_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepEval golden-set runner.")
    parser.add_argument("--quick", action="store_true", help="Only first 2 cases.")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    setup_logging()

    # Point DeepEval at the same gateway the app uses
    settings = get_settings()
    if settings.openai_base_url:
        os.environ.setdefault("OPENAI_BASE_URL", settings.openai_base_url)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

    cases = GOLDEN_CASES[:2] if args.quick else GOLDEN_CASES
    logger.info("Running DeepEval on {} cases.", len(cases))

    test_cases = [_run_one(c) for c in cases]
    metrics = _build_metrics(model_name=args.model)

    from deepeval import evaluate

    results = evaluate(test_cases=test_cases, metrics=metrics)

    # Build per-case summary
    case_records = []
    metric_totals: dict[str, list[float]] = {}

    for tc, case in zip(test_cases, cases):
        scores: dict[str, float | None] = {}
        passed: dict[str, bool] = {}
        for m in metrics:
            name = m.name
            score = getattr(m, "score", None)
            scores[name] = round(float(score), 4) if score is not None else None
            passed[name] = getattr(m, "is_successful", lambda: None)()
            if score is not None:
                metric_totals.setdefault(name, []).append(float(score))
        case_records.append({
            "query": case.query,
            "expected_concepts": case.expected_concepts,
            "scores": scores,
            "passed": passed,
        })

    metrics_summary = {
        name: round(sum(vals) / len(vals), 4)
        for name, vals in metric_totals.items()
    }
    logger.info("Aggregate scores: {}", metrics_summary)
    _save_results(case_records, metrics_summary)


if __name__ == "__main__":
    main()
