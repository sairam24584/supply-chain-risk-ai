"""Expose stored DeepEval results via REST."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/eval", tags=["eval"])

RESULTS_PATH = Path(__file__).resolve().parents[4] / "data" / "eval_results.json"


@router.get("/results")
async def get_eval_results() -> dict:
    """Return the latest DeepEval run results from data/eval_results.json."""
    if not RESULTS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No eval results found. Run: python -m scripts.eval from backend/",
        )
    return json.loads(RESULTS_PATH.read_text())
