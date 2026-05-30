"""Endpoints exposing the Phase 1 intelligence layer:

  * Anomalies (IsolationForest)
  * Correlations (numeric + categorical)
  * Forecast & stockout prediction
  * Region (cross-location) disruption analysis
"""
from fastapi import APIRouter, HTTPException, Query

from app.services import anomaly, intelligence

router = APIRouter(prefix="/api", tags=["intelligence"])


@router.get("/anomalies")
async def anomalies() -> dict:
    return anomaly.get_anomaly_summary()


@router.get("/correlations")
async def correlations() -> dict:
    return intelligence.get_correlations()


@router.get("/forecast/{sku}")
async def forecast(sku: str) -> dict:
    out = intelligence.forecast_for_sku(sku)
    if out is None:
        raise HTTPException(status_code=404, detail=f"SKU '{sku}' not found")
    return out


@router.get("/stockout-prediction")
async def stockout_prediction(top_n: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return intelligence.stockout_predictions(top_n=top_n)


@router.get("/regions/risk")
async def region_risk() -> dict:
    return intelligence.region_risk_summary()
