"""Proactive disruption alerts endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services.alerting import get_alert_summary, get_alerts, scan_and_alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[dict[str, Any]])
async def list_alerts(
    category: str | None = Query(default=None, description="supplier|shipment|inventory|anomaly"),
    severity: str | None = Query(default=None, description="high|medium|low"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Return stored proactive alerts, newest first."""
    return get_alerts(category=category, severity=severity, limit=limit, offset=offset)


@router.get("/summary")
async def alert_summary() -> dict[str, Any]:
    """Counts by category and severity."""
    return get_alert_summary()


@router.post("/scan")
async def trigger_scan() -> dict[str, Any]:
    """Manually trigger a threshold scan (APScheduler runs this automatically)."""
    new_count = scan_and_alert()
    return {"new_alerts": new_count}
