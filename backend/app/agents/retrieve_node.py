"""Retrieval node — hybrid Chroma + BM25 + RRF + rerank + context compression.

Pulls both vector hits and live analytics snapshots so downstream specialist
agents have grounded context without making their own DB calls.
"""
from __future__ import annotations

from typing import Any

from app.agents.query_preprocessor import compress_context
from app.agents.state import AgentState
from app.core.logging import logger
from app.services import analytics, intelligence
from app.services.retriever import get_retriever


def retrieve_node(state: AgentState) -> dict[str, Any]:
    """Run hybrid retrieval and attach analytics snapshots to state."""
    retriever = get_retriever()
    hits = retriever.retrieve(
        query=state.get("query_rewritten") or state["query"],
        top_k=state.get("top_k") or 8,
        where=state.get("filters"),
        rerank=True,
    )
    compressed = compress_context(hits, max_chars_per_chunk=220, max_chunks=5)
    logger.info("retrieve_node | hits={} compressed_chunks={}", len(hits), len(compressed))

    # ── Live analytics snapshots ──────────────────────────────────────────────
    supplier_snapshot  = analytics.supplier_risk_ranking(top_n=5)
    shipment_snapshot  = analytics.shipment_risk_summary()
    inventory_snapshot = analytics.inventory_risk_list(top_n=8)
    correlations       = intelligence.get_correlations()
    region_snapshot    = intelligence.region_risk_summary()
    stockout_snapshot  = intelligence.stockout_predictions(top_n=5)

    cross = {
        "top_numeric_correlations":      correlations["numeric"][:3],
        "top_categorical_associations":  correlations["categorical"][:3],
        "hotspot_region":                region_snapshot.get("hotspot"),
        "top_disrupted_regions":         region_snapshot.get("top_disrupted", [])[:3],
        "imminent_stockouts":            stockout_snapshot[:5],
    }

    return {
        "retrieved_hits":     hits,
        "compressed_hits":    compressed,
        "supplier_analytics": {"top_5": supplier_snapshot},
        "shipment_analytics": {
            "hotspots":        shipment_snapshot["hotspots"][:5],
            "by_mode":         shipment_snapshot["by_transport_mode"],
            "total_delay_rate": shipment_snapshot["delay_rate"],
        },
        "inventory_analytics": {
            "at_risk":              inventory_snapshot,
            "stockout_predictions": stockout_snapshot,
        },
        "cross_signals":  cross,
        "agents_invoked": ["retriever"],
    }


__all__ = ["retrieve_node"]
