"""Auto-retry loop for low-quality responses.

Wraps the LangGraph pipeline so that when the Judge Agent's `overall_quality`
score is below the configured threshold we re-invoke the graph (up to N
additional times). Each retry runs against a fresh `attempt` counter so prompts
can vary their phrasing if desired.
"""
from __future__ import annotations

from typing import Any, Callable

from app.core.logging import logger

DEFAULT_THRESHOLD = 0.5
DEFAULT_MAX_RETRIES = 1


def run_with_retry(
    runner: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]],
    initial_state: dict[str, Any],
    config: dict[str, Any] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[dict[str, Any], int, list[float]]:
    """Run the agent graph, optionally retry if Judge quality is below threshold.

    Returns (final_state, attempts, judge_scores_per_attempt).
    """
    scores: list[float] = []
    attempts = 0
    state = initial_state

    while True:
        attempts += 1
        final = runner(state, config)
        judge = (final or {}).get("judge_verdict") or {}
        score = float(judge.get("overall_quality", 0.0))
        scores.append(score)

        if score >= threshold or attempts > max_retries:
            if attempts > 1:
                logger.info(
                    "retry_loop done | attempts={} scores={}", attempts, scores
                )
            return final, attempts, scores

        logger.warning(
            "retry_loop quality {} < threshold {} (attempt {}); retrying", score, threshold, attempts
        )
        # On retry: keep the question, drop downstream state so the graph reruns.
        state = {
            "query": initial_state["query"],
            "filters": initial_state.get("filters"),
            "top_k": initial_state.get("top_k"),
        }


__all__ = ["run_with_retry"]
