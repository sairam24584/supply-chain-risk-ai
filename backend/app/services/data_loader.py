"""Load the supply-chain CSV, derive risk fields, and turn rows into incident narratives.

The CSV is structured operational data. To make it usable for semantic retrieval we
synthesize a short natural-language "incident record" per row plus a metadata dict
that the vector store can filter on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


# --- Risk derivation thresholds (single source of truth) ---
DEFECT_HIGH = 3.0
DEFECT_MED = 1.0
STOCKOUT_THRESHOLD = 20
OVERSTOCK_THRESHOLD = 80
SHIPPING_DELAY_HIGH = 8
LEAD_TIME_LONG = 25

SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}


@dataclass
class IncidentRecord:
    """One narrative + metadata pair, ready for embedding."""

    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _defect_severity(defect_rate: float) -> str:
    if defect_rate >= DEFECT_HIGH:
        return "high"
    if defect_rate >= DEFECT_MED:
        return "medium"
    return "low"


def _stock_status(stock_level: int) -> str:
    if stock_level <= STOCKOUT_THRESHOLD:
        return "stockout_risk"
    if stock_level >= OVERSTOCK_THRESHOLD:
        return "overstock"
    return "healthy"


def _delay_status(shipping_time: int, lead_time: int) -> str:
    if shipping_time >= SHIPPING_DELAY_HIGH or lead_time >= LEAD_TIME_LONG:
        return "delayed"
    if shipping_time >= 5:
        return "moderate"
    return "on_time"


def _overall_severity(defect: str, stock: str, delay: str, inspection: str) -> str:
    """Aggregate per-row severity into a single bucket."""
    score = SEVERITY_WEIGHTS[defect]
    if stock == "stockout_risk":
        score += 2
    if delay == "delayed":
        score += 2
    if inspection == "Fail":
        score += 3
    elif inspection == "Pending":
        score += 1
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _row_to_narrative(row: pd.Series) -> str:
    """Convert one CSV row into a compact, embedding-friendly incident record."""
    return (
        f"Incident record for SKU {row['SKU']} ({row['Product type']}).\n"
        f"Supplier: {row['Supplier name']} based in {row['Location']}. "
        f"Stock level is {row['Stock levels']} units (status: {row['stock_status']}); "
        f"order quantity {row['Order quantities']}, production volume {row['Production volumes']}.\n"
        f"Shipping via {row['Shipping carriers']} on {row['Transportation modes']} "
        f"({row['Routes']}). Shipping time {row['Shipping times']} days, "
        f"lead time {row['Lead time']} days, manufacturing lead time "
        f"{row['Manufacturing lead time']} days. Delay status: {row['delay_status']}.\n"
        f"Quality inspection: {row['Inspection results']}; defect rate "
        f"{row['Defect rates']:.2f}% (severity {row['defect_severity']}).\n"
        f"Financials: price ${row['Price']:.2f}, revenue ${row['Revenue generated']:.2f}, "
        f"shipping cost ${row['Shipping costs']:.2f}, manufacturing cost "
        f"${row['Manufacturing costs']:.2f}, total logistics cost ${row['Costs']:.2f}.\n"
        f"Overall risk severity: {row['risk_severity']}."
    )


def load_dataframe(csv_path: Path) -> pd.DataFrame:
    """Read the CSV and add derived risk columns + anomaly scores.

    Pure function — no I/O side effects beyond reading the CSV.
    """
    df = pd.read_csv(csv_path)
    df["defect_severity"] = df["Defect rates"].apply(_defect_severity)
    df["stock_status"] = df["Stock levels"].apply(_stock_status)
    df["delay_status"] = df.apply(
        lambda r: _delay_status(int(r["Shipping times"]), int(r["Lead time"])), axis=1
    )
    df["risk_severity"] = df.apply(
        lambda r: _overall_severity(
            r["defect_severity"], r["stock_status"], r["delay_status"], r["Inspection results"]
        ),
        axis=1,
    )

    # Layered anomaly detection (IsolationForest) — local import avoids a
    # circular dep with services.anomaly which imports load_dataframe via analytics.
    from app.services.anomaly import annotate_with_anomalies

    df = annotate_with_anomalies(df)
    return df


def build_incident_records(df: pd.DataFrame) -> list[IncidentRecord]:
    """Convert an enriched dataframe into IncidentRecord list."""
    records: list[IncidentRecord] = []
    for _, row in df.iterrows():
        # Pull anomaly fields if present (annotate_with_anomalies has been called)
        anom_score = float(row["anomaly_score"]) if "anomaly_score" in row else 0.0
        anom_label = int(row["anomaly_label"]) if "anomaly_label" in row else 1
        meta = {
            "sku": str(row["SKU"]),
            "product_type": str(row["Product type"]),
            "supplier": str(row["Supplier name"]),
            "location": str(row["Location"]),
            "carrier": str(row["Shipping carriers"]),
            "transport_mode": str(row["Transportation modes"]),
            "route": str(row["Routes"]),
            "inspection": str(row["Inspection results"]),
            "defect_severity": str(row["defect_severity"]),
            "stock_status": str(row["stock_status"]),
            "delay_status": str(row["delay_status"]),
            "risk_severity": str(row["risk_severity"]),
            "defect_rate": float(row["Defect rates"]),
            "stock_level": int(row["Stock levels"]),
            "shipping_time_days": int(row["Shipping times"]),
            "lead_time_days": int(row["Lead time"]),
            "revenue": float(row["Revenue generated"]),
            "shipping_cost": float(row["Shipping costs"]),
            "total_cost": float(row["Costs"]),
            "anomaly_score": anom_score,
            "anomaly_label": anom_label,
        }
        records.append(
            IncidentRecord(
                doc_id=f"incident-{row['SKU']}",
                text=_row_to_narrative(row),
                metadata=meta,
            )
        )
    return records


__all__ = [
    "IncidentRecord",
    "load_dataframe",
    "build_incident_records",
]
