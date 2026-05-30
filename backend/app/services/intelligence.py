"""Higher-order supply-chain intelligence built on top of the enriched dataframe.

Provides four families of analytics used by both API endpoints and the agent
prompts:

  1. Cross-signal correlations  (numeric Pearson + categorical chi-square)
  2. Demand forecast            (per-SKU linear trend + days-to-stockout)
  3. Stockout predictions       (sorted by urgency)
  4. Region risk aggregation    (cross-region disruption analysis)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from app.services.analytics import get_df

# ---------------------------------------------------------------------------
# 1. Correlations
# ---------------------------------------------------------------------------

_NUMERIC_PAIRS = [
    ("Defect rates", "Lead time"),
    ("Defect rates", "Shipping times"),
    ("Defect rates", "Costs"),
    ("Lead time", "Shipping times"),
    ("Lead time", "Manufacturing lead time"),
    ("Shipping times", "Costs"),
    ("Stock levels", "Number of products sold"),
    ("Production volumes", "Number of products sold"),
    ("Manufacturing costs", "Defect rates"),
]


def _pearson(df: pd.DataFrame, a: str, b: str) -> float:
    s = df[[a, b]].dropna()
    if len(s) < 3:
        return 0.0
    return float(s[a].corr(s[b]))


def _chi_square(df: pd.DataFrame, a: str, b: str) -> dict[str, Any]:
    """Cheap chi-square style association strength (Cramér's V) for categoricals."""
    from scipy.stats import chi2_contingency

    table = pd.crosstab(df[a], df[b])
    if table.size == 0:
        return {"cramers_v": 0.0, "p_value": 1.0}
    chi2, p, _, _ = chi2_contingency(table)
    n = table.values.sum()
    r, k = table.shape
    denom = n * (min(r - 1, k - 1) or 1)
    v = float(np.sqrt(chi2 / denom)) if denom > 0 else 0.0
    return {"cramers_v": round(v, 3), "p_value": round(float(p), 4)}


@lru_cache
def get_correlations() -> dict[str, Any]:
    df = get_df()

    numeric = []
    for a, b in _NUMERIC_PAIRS:
        if a in df.columns and b in df.columns:
            numeric.append(
                {"a": a, "b": b, "pearson": round(_pearson(df, a, b), 3)}
            )

    categorical = [
        {"a": "Supplier name", "b": "Inspection results", **_chi_square(df, "Supplier name", "Inspection results")},
        {"a": "Shipping carriers", "b": "delay_status", **_chi_square(df, "Shipping carriers", "delay_status")},
        {"a": "Transportation modes", "b": "delay_status", **_chi_square(df, "Transportation modes", "delay_status")},
        {"a": "Location", "b": "risk_severity", **_chi_square(df, "Location", "risk_severity")},
        {"a": "Routes", "b": "delay_status", **_chi_square(df, "Routes", "delay_status")},
    ]

    # Sort: numeric by absolute strength, categorical by Cramér's V
    numeric.sort(key=lambda x: abs(x["pearson"]), reverse=True)
    categorical.sort(key=lambda x: x["cramers_v"], reverse=True)

    return {"numeric": numeric, "categorical": categorical}


# ---------------------------------------------------------------------------
# 2. Demand forecast & stockout prediction
# ---------------------------------------------------------------------------

def _forecast_row(row: pd.Series, horizon_days: int = 30) -> dict[str, Any]:
    """Per-SKU forecast — uses sales velocity to project demand over `horizon_days`.

    Velocity is derived from `Number of products sold` (treated as units/period
    since the CSV has no timestamps). Days-to-stockout = stock / velocity.
    """
    units_sold = float(row["Number of products sold"])
    stock = float(row["Stock levels"])
    daily_velocity = max(units_sold / 30.0, 0.0)   # assume 30-day window
    forecast_units = daily_velocity * horizon_days
    days_to_stockout = (stock / daily_velocity) if daily_velocity > 0 else float("inf")

    if days_to_stockout < 7:
        urgency = "critical"
    elif days_to_stockout < 14:
        urgency = "high"
    elif days_to_stockout < 30:
        urgency = "medium"
    else:
        urgency = "low"

    return {
        "sku": str(row["SKU"]),
        "product_type": str(row["Product type"]),
        "supplier": str(row["Supplier name"]),
        "location": str(row["Location"]),
        "stock_level": int(stock),
        "daily_velocity": round(daily_velocity, 2),
        "forecast_units": round(forecast_units, 1),
        "days_to_stockout": round(days_to_stockout, 1) if np.isfinite(days_to_stockout) else None,
        "urgency": urgency,
    }


def forecast_for_sku(sku: str) -> dict[str, Any] | None:
    df = get_df()
    rows = df[df["SKU"] == sku]
    if rows.empty:
        return None
    return _forecast_row(rows.iloc[0])


def stockout_predictions(top_n: int = 20) -> list[dict[str, Any]]:
    df = get_df()
    rows = [_forecast_row(r) for _, r in df.iterrows()]
    rows = [r for r in rows if r["days_to_stockout"] is not None]
    rows.sort(key=lambda r: r["days_to_stockout"])
    return rows[:top_n]


# ---------------------------------------------------------------------------
# 3. Region (location) risk aggregation
# ---------------------------------------------------------------------------

@lru_cache
def region_risk_summary() -> dict[str, Any]:
    df = get_df()
    grouped = df.groupby("Location").agg(
        skus=("SKU", "count"),
        suppliers=("Supplier name", "nunique"),
        avg_defect_rate=("Defect rates", "mean"),
        fail_inspections=("Inspection results", lambda s: int((s == "Fail").sum())),
        high_severity=("risk_severity", lambda s: int((s == "high").sum())),
        delayed=("delay_status", lambda s: int((s == "delayed").sum())),
        stockout_risk=("stock_status", lambda s: int((s == "stockout_risk").sum())),
        anomalies=("anomaly_label", lambda s: int((s == -1).sum())) if "anomaly_label" in df.columns else ("SKU", "count"),
        revenue=("Revenue generated", "sum"),
    )
    grouped["disruption_index"] = (
        grouped["high_severity"] * 1.5
        + grouped["fail_inspections"] * 1.2
        + grouped["delayed"]
        + grouped["stockout_risk"] * 1.3
        + grouped["anomalies"]
    ).round(2)
    grouped = grouped.sort_values("disruption_index", ascending=False).reset_index()

    records = []
    for r in grouped.to_dict(orient="records"):
        records.append(
            {k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()}
        )
    return {
        "total_regions": int(grouped.shape[0]),
        "top_disrupted": records,
        "hotspot": records[0]["Location"] if records else None,
    }


def clear_cache() -> None:
    get_correlations.cache_clear()
    region_risk_summary.cache_clear()


__all__ = [
    "get_correlations",
    "forecast_for_sku",
    "stockout_predictions",
    "region_risk_summary",
    "clear_cache",
]
