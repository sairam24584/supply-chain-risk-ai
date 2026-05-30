"""Query preprocessing — rewrite, intent detection, prompt compression.

A single deterministic-first pass that runs BEFORE the retrieval step. Uses
the LLM only when the heuristics are ambiguous, so it adds minimal latency.

Pipeline:
  rewrite()                  — expand pronouns / abbreviations, normalise casing
  detect_intent()            — classify into a supply-chain intent label
  compress_context()         — diversify & dedupe retrieved chunks before prompts
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from app.core.logging import logger

# ---------- intent labels ----------

IntentLabel = Literal[
    "supplier_quality",
    "shipment_logistics",
    "inventory_demand",
    "anomaly_review",
    "region_disruption",
    "mitigation_recommendation",
    "general_overview",
]

_INTENT_KEYWORDS: dict[IntentLabel, list[str]] = {
    "supplier_quality":           ["supplier", "vendor", "defect", "quality", "inspection", "fail"],
    "shipment_logistics":         ["shipment", "shipping", "carrier", "route", "transport", "delivery", "delay"],
    "inventory_demand":           ["inventory", "stock", "stockout", "overstock", "demand", "forecast"],
    "anomaly_review":             ["anomaly", "anomalous", "outlier", "unusual"],
    "region_disruption":          ["region", "location", "warehouse", "city", "country", "cross-region"],
    "mitigation_recommendation":  ["mitigation", "action", "recommend", "plan", "fix", "remediation"],
}

# ---------- rewrite ----------

_ABBREVS = {
    r"\bSC\b":     "supply chain",
    r"\bSKU\b":    "stock keeping unit (SKU)",
    r"\bPO\b":     "purchase order",
    r"\bETA\b":    "estimated time of arrival",
    r"\bTAT\b":    "turnaround time",
    r"\bQA\b":     "quality assurance",
    r"\bRCA\b":    "root cause analysis",
    r"\bKPI\b":    "key performance indicator",
    r"\bOTD\b":    "on-time delivery",
}

@dataclass
class PreprocessedQuery:
    original: str
    rewritten: str
    intent: IntentLabel
    intent_confidence: float
    notes: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "rewritten": self.rewritten,
            "intent": self.intent,
            "intent_confidence": self.intent_confidence,
            "notes": self.notes,
        }


def rewrite(query: str) -> tuple[str, list[str]]:
    """Heuristic rewrite: expand common SC abbreviations + collapse whitespace."""
    notes: list[str] = []
    rewritten = re.sub(r"\s+", " ", query).strip()
    expanded = rewritten
    for pat, repl in _ABBREVS.items():
        if re.search(pat, expanded):
            expanded = re.sub(pat, repl, expanded)
            notes.append("expanded:" + pat.replace("\\b", ""))
    return expanded, notes


def detect_intent(query: str) -> tuple[IntentLabel, float]:
    """Lexical intent classifier. Returns (label, confidence in [0,1])."""
    lower = query.lower()
    scores: dict[IntentLabel, int] = {k: 0 for k in _INTENT_KEYWORDS}
    for label, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[label] += 1
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if total == 0:
        return "general_overview", 0.3
    confidence = round(scores[best] / total, 2)
    return best, confidence


def preprocess_query(query: str) -> PreprocessedQuery:
    rewritten, notes = rewrite(query)
    intent, conf = detect_intent(rewritten)
    logger.info("query preprocess | intent={} conf={}", intent, conf)
    return PreprocessedQuery(
        original=query,
        rewritten=rewritten,
        intent=intent,
        intent_confidence=conf,
        notes=notes,
    )


# ---------- prompt compression ----------

def _normalise_sentence(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def compress_context(
    hits: list[dict[str, Any]],
    max_chars_per_chunk: int = 220,
    max_chunks: int = 5,
    dedupe_sentence_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Reduce retrieved hits to a token-efficient, low-redundancy subset.

    Strategy (no extra ML deps — pure heuristics):
      1. Truncate each chunk to `max_chars_per_chunk` after preferring the
         first 2 sentences (usually most informative).
      2. Drop chunks whose normalised first sentence overlaps > threshold
         with one already kept (cheap dedup).
      3. Keep at most `max_chunks`.
    """
    if not hits:
        return hits

    kept: list[dict[str, Any]] = []
    kept_first_sentences: list[set[str]] = []

    for h in hits:
        text = (h.get("text") or "")
        # First two sentences preferred
        sentences = re.split(r"(?<=[.!?])\s+", text)
        head = " ".join(sentences[:2]).strip() or text
        head = head[:max_chars_per_chunk].strip()

        first_norm = _normalise_sentence(sentences[0] if sentences else "")
        first_tokens = set(first_norm.split())

        # cheap Jaccard dedup
        is_dup = False
        for prev in kept_first_sentences:
            if not prev or not first_tokens:
                continue
            inter = len(first_tokens & prev)
            union = len(first_tokens | prev) or 1
            if inter / union >= dedupe_sentence_threshold:
                is_dup = True
                break
        if is_dup:
            continue

        new_hit = {**h, "text": head, "compressed": True}
        kept.append(new_hit)
        kept_first_sentences.append(first_tokens)
        if len(kept) >= max_chunks:
            break

    return kept


__all__ = [
    "IntentLabel",
    "PreprocessedQuery",
    "rewrite",
    "detect_intent",
    "preprocess_query",
    "compress_context",
]
