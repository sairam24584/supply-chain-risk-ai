"""Deterministic analytics endpoints for dashboard tiles + drill-down views.

These complement the LLM-powered /api/query route — same data, no model cost.
"""
from fastapi import APIRouter, HTTPException, Query

from app.services import analytics

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/dashboard/summary")
async def dashboard_summary() -> dict:
    return analytics.dashboard_summary()


@router.get("/suppliers/risk")
async def supplier_risk(top_n: int = Query(default=10, ge=1, le=50)) -> list[dict]:
    return analytics.supplier_risk_ranking(top_n=top_n)


@router.get("/shipments/risk")
async def shipment_risk() -> dict:
    return analytics.shipment_risk_summary()


@router.get("/inventory/risk")
async def inventory_risk(top_n: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return analytics.inventory_risk_list(top_n=top_n)


@router.get("/incidents/{sku}")
async def incident_detail(sku: str) -> dict:
    rec = analytics.incident_by_sku(sku)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"SKU '{sku}' not found")
    return rec
