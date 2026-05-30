"""Deterministic analytics over the supply-chain dataframe.

These power the dashboard/listing endpoints — no LLM cost. The same enriched
dataframe (via `load_dataframe`) drives both retrieval-time narratives and
these analytical aggregations.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.services.data_loader import load_dataframe


@lru_cache
def get_df() -> pd.DataFrame:
    """Cached enriched dataframe (single source of truth across analytics)."""
    return load_dataframe(get_settings().data_csv_path)


# ---------- supplier risk ----------

def supplier_risk_ranking(top_n: int = 10) -> list[dict[str, Any]]:
    """Aggregate supplier-level risk metrics. Sorted worst-first."""
    df = get_df()
    grouped = df.groupby("Supplier name").agg(
        skus=("SKU", "count"),
        avg_defect_rate=("Defect rates", "mean"),
        max_defect_rate=("Defect rates", "max"),
        fail_inspections=("Inspection results", lambda s: int((s == "Fail").sum())),
        pending_inspections=("Inspection results", lambda s: int((s == "Pending").sum())),
        high_severity_count=("risk_severity", lambda s: int((s == "high").sum())),
        avg_lead_time=("Lead time", "mean"),
        total_revenue=("Revenue generated", "sum"),
    )
    grouped["risk_index"] = (
        grouped["avg_defect_rate"]
        + grouped["fail_inspections"] * 1.5
        + grouped["high_severity_count"] * 1.2
    ).round(2)
    grouped = grouped.sort_values("risk_index", ascending=False).head(top_n).reset_index()
    return _to_records(grouped, rename={"Supplier name": "supplier"})


# ---------- shipment risk ----------

def shipment_risk_summary() -> dict[str, Any]:
    """Carrier × route hotspots + transport-mode delay rates."""
    df = get_df()
    delayed_mask = df["delay_status"] == "delayed"

    carrier_route = (
        df.groupby(["Shipping carriers", "Routes"])
        .agg(
            shipments=("SKU", "count"),
            delayed=("delay_status", lambda s: int((s == "delayed").sum())),
            avg_shipping_time=("Shipping times", "mean"),
            avg_shipping_cost=("Shipping costs", "mean"),
        )
        .reset_index()
    )
    carrier_route["delay_rate"] = (carrier_route["delayed"] / carrier_route["shipments"]).round(2)
    carrier_route = carrier_route.sort_values("delay_rate", ascending=False)

    mode_stats = (
        df.groupby("Transportation modes")
        .agg(
            shipments=("SKU", "count"),
            delayed=("delay_status", lambda s: int((s == "delayed").sum())),
            avg_cost=("Costs", "mean"),
        )
        .reset_index()
    )
    mode_stats["delay_rate"] = (mode_stats["delayed"] / mode_stats["shipments"]).round(2)

    return {
        "total_shipments": int(len(df)),
        "delayed_count": int(delayed_mask.sum()),
        "delay_rate": round(float(delayed_mask.mean()), 3),
        "hotspots": _to_records(
            carrier_route.head(10),
            rename={"Shipping carriers": "carrier", "Routes": "route"},
        ),
        "by_transport_mode": _to_records(
            mode_stats, rename={"Transportation modes": "mode"}
        ),
    }


# ---------- inventory risk ----------
# Stockouts ranked first (most urgent), then overstocks.

def inventory_risk_list(top_n: int = 20) -> list[dict[str, Any]]:
    """SKUs at stockout or overstock risk, with key context for triage.

    Stockouts (most urgent) ranked first, then overstocks.
    """
    df = get_df()
    risky = df[df["stock_status"] != "healthy"].copy()
    # Stockouts first (urgency), then overstocks; within each, lowest/highest stock first.
    priority = {"stockout_risk": 0, "overstock": 1}
    risky["_priority"] = risky["stock_status"].map(priority)
    risky = risky.sort_values(
        by=["_priority", "Stock levels"], ascending=[True, True]
    ).drop(columns="_priority").head(top_n)
    cols = [
        "SKU", "Product type", "Supplier name", "Location",
        "Stock levels", "stock_status", "Order quantities",
        "Number of products sold", "Production volumes",
        "risk_severity",
    ]
    return _to_records(
        risky[cols],
        rename={
            "SKU": "sku",
            "Product type": "product_type",
            "Supplier name": "supplier",
            "Location": "location",
            "Stock levels": "stock_level",
            "Order quantities": "order_quantity",
            "Number of products sold": "units_sold",
            "Production volumes": "production_volume",
        },
    )


# ---------- dashboard summary ----------

def dashboard_summary() -> dict[str, Any]:
    """High-level counts/percentages for dashboard tiles."""
    df = get_df()
    total = int(len(df))
    return {
        "total_skus": total,
        "suppliers": int(df["Supplier name"].nunique()),
        "warehouses": int(df["Location"].nunique()),
        "severity_breakdown": df["risk_severity"].value_counts().to_dict(),
        "stock_status_breakdown": df["stock_status"].value_counts().to_dict(),
        "delay_status_breakdown": df["delay_status"].value_counts().to_dict(),
        "inspection_breakdown": df["Inspection results"].value_counts().to_dict(),
        "avg_defect_rate": round(float(df["Defect rates"].mean()), 2),
        "total_revenue": round(float(df["Revenue generated"].sum()), 2),
        "total_logistics_cost": round(float(df["Costs"].sum()), 2),
        "high_severity_pct": round(
            float((df["risk_severity"] == "high").mean()) * 100, 1
        ),
    }


# ---------- single SKU drill-down ----------

def incident_by_sku(sku: str) -> dict[str, Any] | None:
    df = get_df()
    rows = df[df["SKU"] == sku]
    if rows.empty:
        return None
    rec = rows.iloc[0].to_dict()
    # Coerce numpy types so JSON serialisation works.
    return {k: _py(v) for k, v in rec.items()}


# ---------- internals ----------

def _to_records(df: pd.DataFrame, rename: dict[str, str] | None = None) -> list[dict[str, Any]]:
    if rename:
        df = df.rename(columns=rename)
    out = df.to_dict(orient="records")
    return [{k: _py(v) for k, v in row.items()} for row in out]


def _py(v: Any) -> Any:
    """Convert numpy scalars to native python for JSON encoding."""
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v


__all__ = [
    "supplier_risk_ranking",
    "shipment_risk_summary",
    "inventory_risk_list",
    "dashboard_summary",
    "incident_by_sku",
]
