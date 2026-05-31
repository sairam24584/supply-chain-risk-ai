"""Liveness / readiness endpoint."""
from fastapi import APIRouter

from app.models.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
