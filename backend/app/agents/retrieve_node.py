"""Retrieval node -- hybrid Chroma + BM25 + RRF + rerank + context compression.

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


def _format_supplier_snapshot(rows: list[dict]) -> str:
    """Pre-format supplier analytics as ranked text so LLM cannot mix up fields."""
    lines = ["SUPPLIER RISK RANKING (ground truth -- use these numbers, not context):"]
    for i, r in enumerate(rows, 1):
        lines.append(
            "  Rank %d: %s | overall_risk_score=%.1f | avg_defect_rate=%.2f%% "
            "| failed_inspections=%d | high_severity_incidents=%d" % (
                i,
                r["supplier"],
                r.get("risk_index", 0),
                r.get("avg_defect_rate", 0),
                r.get("fail_inspections", 0),
                r.get("high_severity_count", 0),
            )
        )
    return "\n".join(lines)


def _format_shipment_snapshot(snap: dict) -> str:
    lines = ["SHIPMENT RISK (ground truth):"]
    lines.append("  Network delay rate: %.1f%%" % (snap.get("delay_rate", 0) * 100))
    for h in snap.get("hotspots", [])[:5]:
        lines.append(
            "  %s x %s | delay_rate=%.1f%% | avg_shipping_days=%.1fd" % (
                h.get("carrier", "?"), h.get("route", "?"),
                h.get("delay_rate", 0) * 100, h.get("avg_shipping_time", 0),
            )
        )
    return "\n".join(lines)


def _format_inventory_snapshot(rows: list[dict], stockouts: list[dict]) -> str:
    """Use stockout_predictions (has days_to_stockout) then fall back to inventory_risk_list."""
    lines = ["INVENTORY RISK (ground truth -- rank by days_to_stockout, lowest = most urgent):"]
    # stockouts from intelligence.stockout_predictions always has days_to_stockout
    seen_skus: set[str] = set()
    for r in stockouts[:8]:
        sku = r.get("sku", "?")
        seen_skus.add(sku)
        lines.append(
            "  %s @ %s | stock=%d units | days_to_stockout=%.0f | urgency=%s" % (
                sku, r.get("location", "?"),
                r.get("stock_level", 0),
                r.get("days_to_stockout", 0),
                r.get("urgency", "unknown"),
            )
        )
    # Append remaining at-risk SKUs from analytics not already listed
    for r in rows[:8]:
        sku = r.get("sku", "?")
        if sku not in seen_skus:
            lines.append(
                "  %s @ %s | stock=%d units | status=%s" % (
                    sku, r.get("location", "?"),
                    r.get("stock_level", 0),
                    r.get("stock_status", "unknown"),
                )
            )
    return "\n".join(lines)


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

    # -- Live analytics snapshots -- deterministic, pre-formatted as readable text --
    supplier_rows  = analytics.supplier_risk_ranking(top_n=5)
    shipment_snap  = analytics.shipment_risk_summary()
    inventory_rows = analytics.inventory_risk_list(top_n=8)
    correlations   = intelligence.get_correlations()
    region_snap    = intelligence.region_risk_summary()
    stockout_rows  = intelligence.stockout_predictions(top_n=5)

    cross = {
        "top_numeric_correlations":     correlations["numeric"][:3],
        "top_categorical_associations": correlations["categorical"][:3],
        "hotspot_region":               region_snap.get("hotspot"),
        "top_disrupted_regions":        region_snap.get("top_disrupted", [])[:3],
        "imminent_stockouts":           stockout_rows[:5],
    }

    return {
        "retrieved_hits":     hits,
        "compressed_hits":    compressed,
        # Pre-formatted text snapshots -- agents must use these numbers, not context
        "supplier_analytics":  {"summary": _format_supplier_snapshot(supplier_rows)},
        "shipment_analytics":  {"summary": _format_shipment_snapshot(shipment_snap)},
        "inventory_analytics": {"summary": _format_inventory_snapshot(inventory_rows, stockout_rows)},
        "cross_signals":       cross,
        "agents_invoked":      ["retriever"],
    }


__all__ = ["retrieve_node"]
