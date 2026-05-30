"""Proactive supply chain disruption alerting.

APScheduler runs `scan_and_alert()` every N minutes. Each scan checks the
enriched dataframe against configurable thresholds and writes new alert records
to a SQLite database (data/alerts.db).

Alerts are exposed via GET /api/alerts.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import logger

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "alerts.db"

# ── Thresholds ────────────────────────────────────────────────────────────────
DEFECT_RATE_THRESHOLD = 0.05       # >5% defect rate → supplier alert
DELAY_RATE_THRESHOLD = 0.40        # >40% delayed shipments for a carrier/route
STOCKOUT_THRESHOLD = 50            # stock level < 50 units → inventory alert
ANOMALY_SCORE_THRESHOLD = 0.60     # anomaly_score > 0.60 → anomaly alert
MAX_ALERTS_PER_SCAN = 20           # cap to avoid flooding on first run


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT NOT NULL,
                category    TEXT NOT NULL,   -- supplier | shipment | inventory | anomaly
                severity    TEXT NOT NULL,   -- high | medium | low
                title       TEXT NOT NULL,
                detail      TEXT NOT NULL,
                entity      TEXT,            -- supplier name / route / SKU
                metadata    TEXT            -- JSON blob for extra fields
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_cat ON alerts(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ts  ON alerts(created_at)")


@contextmanager
def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _insert_alert(
    category: str,
    severity: str,
    title: str,
    detail: str,
    entity: str | None = None,
    metadata: dict | None = None,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO alerts (created_at, category, severity, title, detail, entity, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                category,
                severity,
                title,
                detail,
                entity,
                json.dumps(metadata or {}),
            ),
        )


# ── Scan logic ────────────────────────────────────────────────────────────────

def scan_and_alert() -> int:
    """Run threshold checks and store new alerts. Returns count of new alerts."""
    try:
        from app.services.analytics import get_df
    except Exception as exc:
        logger.warning("Alerting scan skipped — could not load dataframe: {}", exc)
        return 0

    _ensure_db()
    df = get_df()
    new_count = 0

    # --- Supplier defect alerts ---
    supplier_defects = (
        df.groupby("Supplier name")["Defect rates"].mean()
        .reset_index()
        .rename(columns={"Defect rates": "avg_defect"})
    )
    risky = supplier_defects[supplier_defects["avg_defect"] > DEFECT_RATE_THRESHOLD]
    for _, row in risky.head(MAX_ALERTS_PER_SCAN).iterrows():
        _insert_alert(
            category="supplier",
            severity="high" if row["avg_defect"] > 0.10 else "medium",
            title=f"High defect rate: {row['Supplier name']}",
            detail=(
                f"Supplier '{row['Supplier name']}' has avg defect rate of "
                f"{row['avg_defect']:.1%} (threshold: {DEFECT_RATE_THRESHOLD:.0%})."
                " Consider quality audit or alternate sourcing."
            ),
            entity=row["Supplier name"],
            metadata={"avg_defect_rate": round(row["avg_defect"], 4)},
        )
        new_count += 1

    # --- Shipment delay alerts ---
    if "delay_status" in df.columns and "Shipping carriers" in df.columns:
        carrier_delay = (
            df.groupby(["Shipping carriers", "Routes"])
            .apply(lambda g: (g["delay_status"] == "delayed").mean())
            .reset_index(name="delay_rate")
        )
        delayed_routes = carrier_delay[carrier_delay["delay_rate"] > DELAY_RATE_THRESHOLD]
        for _, row in delayed_routes.head(MAX_ALERTS_PER_SCAN).iterrows():
            route_label = f"{row['Shipping carriers']} / {row['Routes']}"
            _insert_alert(
                category="shipment",
                severity="high" if row["delay_rate"] > 0.60 else "medium",
                title=f"Chronic delays: {route_label}",
                detail=(
                    f"Route '{route_label}' has {row['delay_rate']:.0%} delay rate "
                    f"(threshold: {DELAY_RATE_THRESHOLD:.0%}). "
                    "Consider carrier switch or re-routing."
                ),
                entity=route_label,
                metadata={"delay_rate": round(row["delay_rate"], 4)},
            )
            new_count += 1

    # --- Inventory stockout alerts ---
    if "Stock levels" in df.columns:
        low_stock = df[df["Stock levels"] < STOCKOUT_THRESHOLD][["SKU", "Stock levels"]].drop_duplicates("SKU")
        for _, row in low_stock.head(MAX_ALERTS_PER_SCAN).iterrows():
            _insert_alert(
                category="inventory",
                severity="high" if row["Stock levels"] < 20 else "medium",
                title=f"Low stock: {row['SKU']}",
                detail=(
                    f"SKU '{row['SKU']}' stock level is {int(row['Stock levels'])} units "
                    f"(threshold: {STOCKOUT_THRESHOLD}). Reorder recommended."
                ),
                entity=row["SKU"],
                metadata={"stock_level": int(row["Stock levels"])},
            )
            new_count += 1

    # --- Anomaly alerts ---
    if "anomaly_score" in df.columns and "anomaly_label" in df.columns:
        anomalies = df[
            (df["anomaly_label"] == -1) & (df["anomaly_score"] > ANOMALY_SCORE_THRESHOLD)
        ][["SKU", "Supplier name", "anomaly_score"]].drop_duplicates("SKU")
        for _, row in anomalies.head(MAX_ALERTS_PER_SCAN).iterrows():
            _insert_alert(
                category="anomaly",
                severity="high",
                title=f"Anomaly detected: {row['SKU']}",
                detail=(
                    f"SKU '{row['SKU']}' (supplier: {row['Supplier name']}) scored "
                    f"{row['anomaly_score']:.2f} anomaly score. "
                    "Multi-feature outlier detected by IsolationForest."
                ),
                entity=row["SKU"],
                metadata={
                    "anomaly_score": round(float(row["anomaly_score"]), 4),
                    "supplier": row["Supplier name"],
                },
            )
            new_count += 1

    if new_count:
        logger.info("Alerting scan complete — {} new alerts generated.", new_count)
    return new_count


# ── Query helpers (used by API route) ────────────────────────────────────────

def get_alerts(
    category: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    _ensure_db()
    filters: list[str] = []
    params: list[Any] = []
    if category:
        filters.append("category = ?")
        params.append(category)
    if severity:
        filters.append("severity = ?")
        params.append(severity)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]
    with _get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_alert_summary() -> dict[str, Any]:
    _ensure_db()
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        by_cat = {
            row["category"]: row["cnt"]
            for row in conn.execute(
                "SELECT category, COUNT(*) as cnt FROM alerts GROUP BY category"
            ).fetchall()
        }
        by_sev = {
            row["severity"]: row["cnt"]
            for row in conn.execute(
                "SELECT severity, COUNT(*) as cnt FROM alerts GROUP BY severity"
            ).fetchall()
        }
        latest = conn.execute(
            "SELECT created_at FROM alerts ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return {
        "total": total,
        "by_category": by_cat,
        "by_severity": by_sev,
        "last_scan": latest[0] if latest else None,
    }
