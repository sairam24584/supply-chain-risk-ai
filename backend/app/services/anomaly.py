"""Multivariate anomaly detection on the supply-chain dataset.

Uses scikit-learn's IsolationForest on the key numeric features:
  defect_rate, lead_time, shipping_time, total_cost, manufacturing_lead_time,
  stock_level, shipping_cost.

The trained model labels each record with:
  * `anomaly_label`  : -1 (anomalous) or 1 (normal)
  * `anomaly_score`  : higher = more anomalous (we invert sklearn's sign convention)

Scores are persisted on the enriched dataframe at ingest time, so they ride
through to retrieval metadata, dashboard analytics, and agent prompts.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

NUMERIC_FEATURES = [
    "Defect rates",
    "Lead time",
    "Shipping times",
    "Costs",
    "Manufacturing lead time",
    "Stock levels",
    "Shipping costs",
]

# Tunables
CONTAMINATION = 0.15        # ~15 % of rows expected anomalous
RANDOM_STATE = 42


def annotate_with_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Fit an IsolationForest and append `anomaly_label`/`anomaly_score`.

    Pure function — operates on a copy, doesn't mutate the caller.
    """
    X = df[NUMERIC_FEATURES].astype(float).to_numpy()

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X)

    raw_labels = model.predict(X)             # -1 anomaly, 1 normal
    raw_scores = model.score_samples(X)       # higher = more normal
    # Invert so higher = more anomalous; normalise to [0,1] for downstream use.
    inverted = -raw_scores
    scaled = (inverted - inverted.min()) / (inverted.max() - inverted.min() + 1e-9)

    out = df.copy()
    out["anomaly_label"] = raw_labels
    out["anomaly_score"] = scaled.round(4)
    return out


@lru_cache
def get_anomaly_summary() -> dict[str, Any]:
    """Cached summary used by the /api/anomalies endpoint and dashboard tile."""
    # Local import avoids a circular dependency at module load.
    from app.services.analytics import get_df

    df = get_df()
    if "anomaly_score" not in df.columns:
        df = annotate_with_anomalies(df)

    anomalies = df[df["anomaly_label"] == -1].sort_values(
        "anomaly_score", ascending=False
    )
    top = anomalies.head(10)[
        [
            "SKU",
            "Product type",
            "Supplier name",
            "Location",
            "Defect rates",
            "Lead time",
            "Shipping times",
            "Costs",
            "anomaly_score",
            "risk_severity",
        ]
    ]
    records = top.rename(
        columns={
            "SKU": "sku",
            "Product type": "product_type",
            "Supplier name": "supplier",
            "Location": "location",
            "Defect rates": "defect_rate",
            "Lead time": "lead_time",
            "Shipping times": "shipping_time",
            "Costs": "total_cost",
        }
    ).to_dict(orient="records")

    # by-supplier and by-region anomaly counts
    by_supplier = (
        anomalies.groupby("Supplier name").size().sort_values(ascending=False).to_dict()
    )
    by_region = (
        anomalies.groupby("Location").size().sort_values(ascending=False).to_dict()
    )

    return {
        "total_anomalies": int(len(anomalies)),
        "anomaly_rate": round(float(len(anomalies)) / max(len(df), 1), 3),
        "by_supplier": {k: int(v) for k, v in by_supplier.items()},
        "by_region": {k: int(v) for k, v in by_region.items()},
        "top_anomalies": [
            {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
            for row in records
        ],
        "features_used": NUMERIC_FEATURES,
        "contamination": CONTAMINATION,
    }


def clear_cache() -> None:
    """Used by ingest when the dataframe is rebuilt."""
    get_anomaly_summary.cache_clear()


__all__ = [
    "NUMERIC_FEATURES",
    "annotate_with_anomalies",
    "get_anomaly_summary",
    "clear_cache",
]
