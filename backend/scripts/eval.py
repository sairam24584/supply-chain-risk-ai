"""DeepEval evaluation harness for the multi-agent assistant.

Runs the live LangGraph pipeline over `GOLDEN_CASES` and scores each output with:
  * FaithfulnessMetric         — answer must be grounded in retrieved context
  * AnswerRelevancyMetric      — answer must address the query
  * GEval (custom rubric)      — mitigation quality (LLM-as-judge)

When OPENAI_API_KEY is not set, falls back to heuristic scoring so results can
still be written to data/eval_results.json without requiring an OpenAI key.

Results are written to data/eval_results.json and can be fetched via GET /api/eval/results.

Usage (from backend/):
    python -m scripts.eval                # full run
    python -m scripts.eval --quick        # only first 2 cases
"""
from __future__ import annotations

# Windows SSL fix — must run before any httpx/openai imports
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import argparse
import json
import os
import re
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


def _run_one(case: GoldenCase) -> dict:
    """Run one golden case through the graph and return raw result dict."""
    graph = get_graph()
    state = graph.invoke(
        {"query": case.query, "top_k": 8},
        config={"configurable": {"thread_id": f"eval-{case.query[:20]}"}},
    )
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
    return {
        "query": case.query,
        "answer": answer or "(no answer)",
        "context": _format_context(hits),
        "expected_concepts": case.expected_concepts,
        "plan": plan,
    }


# ── Heuristic scoring (no OpenAI required) ────────────────────────────────────

def _heuristic_answer_relevancy(query: str, answer: str) -> float:
    """Fraction of query keywords present in the answer."""
    if not answer or answer == "(no answer)":
        return 0.0
    q_words = set(re.findall(r"[a-z]+", query.lower())) - {"the", "a", "an", "of", "for", "in", "are", "with", "what", "which", "is", "do", "we", "our", "and", "to", "on"}
    if not q_words:
        return 1.0
    hits = sum(1 for w in q_words if w in answer.lower())
    return round(hits / len(q_words), 4)


def _heuristic_faithfulness(answer: str, context: list[str]) -> float:
    """Fraction of answer sentences that share at least one keyword with context."""
    if not answer or answer == "(no answer)" or not context:
        return 0.0
    ctx_text = " ".join(context).lower()
    sentences = [s.strip() for s in re.split(r"[.!\n]", answer) if len(s.strip()) > 10]
    if not sentences:
        return 0.0
    grounded = 0
    for sent in sentences:
        words = set(re.findall(r"[a-z]{4,}", sent.lower()))
        if any(w in ctx_text for w in words):
            grounded += 1
    return round(grounded / len(sentences), 4)


def _heuristic_mitigation_quality(answer: str, plan: dict | None) -> float:
    """Simple rubric: has actions + owner + timeframe + risk score."""
    if not plan:
        return 0.2 if (answer and answer != "(no answer)") else 0.0
    score = 0.0
    actions = plan.get("actions") or []
    if actions:
        score += 0.4
        has_owner = any(a.get("owner_role") for a in actions)
        has_time = any(a.get("timeframe_days") for a in actions)
        if has_owner:
            score += 0.2
        if has_time:
            score += 0.2
    if plan.get("risk_score") is not None:
        score += 0.1
    if plan.get("risk_score_justification"):
        score += 0.1
    return round(min(score, 1.0), 4)


def _score_heuristic(result: dict) -> dict[str, float]:
    return {
        "Answer Relevancy":   _heuristic_answer_relevancy(result["query"], result["answer"]),
        "Faithfulness":       _heuristic_faithfulness(result["answer"], result["context"]),
        "Mitigation Quality": _heuristic_mitigation_quality(result["answer"], result.get("plan")),
    }


# ── DeepEval scoring (requires OPENAI_API_KEY) ────────────────────────────────

def _score_deepeval(results: list[dict], model_name: str) -> list[dict[str, float]]:
    from deepeval import evaluate
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    test_cases = [
        LLMTestCase(
            input=r["query"],
            actual_output=r["answer"],
            retrieval_context=r["context"],
            expected_output="; ".join(r["expected_concepts"]),
        )
        for r in results
    ]

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
    metrics = [
        FaithfulnessMetric(threshold=0.7, model=model_name),
        AnswerRelevancyMetric(threshold=0.7, model=model_name),
        mitigation_rubric,
    ]

    evaluate(test_cases=test_cases, metrics=metrics)

    scored = []
    for tc in test_cases:
        row: dict[str, float] = {}
        for m in metrics:
            score = getattr(m, "score", None)
            row[m.name] = round(float(score), 4) if score is not None else 0.0
        scored.append(row)
    return scored


# ── Persistence ───────────────────────────────────────────────────────────────

def _save_results(case_results: list[dict], metrics_summary: dict, mode: str) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "num_cases": len(case_results),
        "scoring_mode": mode,
        "metrics_summary": metrics_summary,
        "cases": case_results,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2))
    logger.info("Eval results saved to {}", RESULTS_PATH)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="DeepEval golden-set runner.")
    parser.add_argument("--quick", action="store_true", help="Only first 2 cases.")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    setup_logging()

    settings = get_settings()
    if settings.openai_base_url:
        os.environ.setdefault("OPENAI_BASE_URL", settings.openai_base_url)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

    cases = GOLDEN_CASES[:2] if args.quick else GOLDEN_CASES
    logger.info("Running DeepEval on {} cases.", len(cases))

    # Run pipeline for all cases first
    results = [_run_one(c) for c in cases]

    # Choose scoring mode
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    if has_openai:
        logger.info("Scoring with DeepEval LLM-as-judge (model={})", args.model)
        try:
            scores_list = _score_deepeval(results, args.model)
            mode = "deepeval"
        except Exception as exc:
            logger.warning("DeepEval scoring failed ({}), falling back to heuristics.", exc)
            scores_list = [_score_heuristic(r) for r in results]
            mode = "heuristic"
    else:
        logger.info("No OPENAI_API_KEY — using heuristic scoring.")
        scores_list = [_score_heuristic(r) for r in results]
        mode = "heuristic"

    # Build per-case records
    case_records = []
    metric_totals: dict[str, list[float]] = {}

    for result, scores in zip(results, scores_list):
        passed = {k: v >= 0.7 for k, v in scores.items()}
        for k, v in scores.items():
            metric_totals.setdefault(k, []).append(v)
        case_records.append({
            "query": result["query"],
            "expected_concepts": result["expected_concepts"],
            "scores": scores,
            "passed": passed,
        })

    metrics_summary = {
        name: round(sum(vals) / len(vals), 4)
        for name, vals in metric_totals.items()
    }
    logger.info("Aggregate scores ({}): {}", mode, metrics_summary)
    _save_results(case_records, metrics_summary, mode)


if __name__ == "__main__":
    main()
