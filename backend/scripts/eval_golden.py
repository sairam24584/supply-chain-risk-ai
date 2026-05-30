"""Golden test set for the supply-chain assistant.

Each case is a (query, expected_concepts) tuple. `expected_concepts` is a list
of keywords/entities the recommendation SHOULD mention — used as a cheap
weak-supervision signal for AnswerRelevance and as ground truth for G-Eval.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoldenCase:
    query: str
    expected_concepts: list[str]
    rationale: str


GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        query="Which suppliers are creating the most quality risk?",
        expected_concepts=["defect", "inspection", "Fail", "supplier"],
        rationale="Should surface high-defect suppliers and failed inspections.",
    ),
    GoldenCase(
        query="Are there shipment routes with chronic delays we should re-route?",
        expected_concepts=["delay", "route", "carrier", "shipping"],
        rationale="Should mention specific carrier/route hotspots.",
    ),
    GoldenCase(
        query="Which SKUs are at imminent stockout risk and what do we do?",
        expected_concepts=["stockout", "stock", "SKU", "restock"],
        rationale="Should identify low-stock SKUs and propose mitigation.",
    ),
    GoldenCase(
        query="Give me a cross-region view of supply chain disruptions.",
        expected_concepts=["location", "region", "supplier", "delay"],
        rationale="Should pull location-level data and patterns.",
    ),
    GoldenCase(
        query="Recommend a mitigation plan for the highest severity incidents.",
        expected_concepts=["mitigation", "audit", "action", "owner"],
        rationale="Should produce concrete owner+timeframe actions.",
    ),
]


__all__ = ["GoldenCase", "GOLDEN_CASES"]
