"""Upload endpoints for documents (PDF/TXT/MD) and CSV (replace dataset).

Documents are embedded into the same Chroma collection as the CSV-derived
incident narratives, with metadata `doc_type="user_doc"` so retrieval can
distinguish them. CSV uploads validate schema, replace the source file, and
trigger a re-ingest of the whole pipeline.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.logging import logger
from app.services import analytics, anomaly, intelligence
from app.services.chunking import chunk_records
from app.services.data_loader import build_incident_records, load_dataframe
from app.services.document_ingestor import (
    MAX_BYTES,
    delete_upload,
    ingest_document,
    ingest_url,
    list_uploads,
    save_upload,
)
from app.services.document_loaders import ALLOWED_EXTS
from app.services.query_cache import get_query_cache
from app.services.retriever import get_retriever
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Columns the CSV pipeline relies on. Anything missing → reject upload.
REQUIRED_CSV_COLUMNS = [
    "SKU", "Product type", "Supplier name", "Location",
    "Stock levels", "Defect rates", "Inspection results",
    "Shipping carriers", "Routes", "Transportation modes",
    "Shipping times", "Lead time", "Manufacturing lead time",
    "Order quantities", "Production volumes",
    "Price", "Revenue generated", "Manufacturing costs",
    "Shipping costs", "Costs", "Number of products sold",
]


@router.post("/document")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """PDF / TXT / MD → chunked + embedded into Chroma as supplementary context."""
    if not file.filename:
        raise HTTPException(400, "file has no filename")
    blob = await file.read()
    try:
        path = save_upload(file.filename, blob)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    try:
        stats = ingest_document(path)
    except Exception as exc:
        logger.exception("Document ingestion failed: {}", exc)
        raise HTTPException(500, f"ingestion failed: {exc}")

    # Invalidate caches so the new chunks can be retrieved + tracked
    get_query_cache().clear()
    get_retriever.cache_clear()  # type: ignore[attr-defined]

    return {"status": "ok", **stats}


@router.post("/csv")
async def upload_csv(file: UploadFile = File(...)) -> dict:
    """Replace the source CSV and re-run the full ingest pipeline."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "expected a .csv file")
    blob = await file.read()
    if len(blob) > MAX_BYTES:
        raise HTTPException(400, f"file too large (>{MAX_BYTES} bytes)")

    # Validate schema before overwriting anything
    settings = get_settings()
    tmp = settings.chroma_persist_dir.parent / "uploads" / f"_pending_{file.filename}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(blob)
    try:
        sample = pd.read_csv(tmp, nrows=5)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, f"CSV unreadable: {exc}")

    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in sample.columns]
    if missing:
        tmp.unlink(missing_ok=True)
        raise HTTPException(
            400,
            {"message": "CSV is missing required columns", "missing": missing},
        )

    # Replace canonical dataset
    target = settings.data_csv_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp), str(target))
    logger.info("Replaced dataset CSV: {}", target)

    # Re-ingest: drop existing collection then rebuild from new CSV
    df = load_dataframe(target)
    records = build_incident_records(df)
    chunks = chunk_records(records)

    store = get_vector_store()
    store.reset()
    n = store.upsert(chunks)

    # Clear all derived caches
    analytics.get_df.cache_clear()
    anomaly.clear_cache()
    intelligence.clear_cache()
    get_query_cache().clear()
    get_retriever.cache_clear()  # type: ignore[attr-defined]

    return {
        "status": "ok",
        "rows": int(len(df)),
        "chunks": len(chunks),
        "upserted": n,
        "severity_breakdown": df["risk_severity"].value_counts().to_dict(),
        "csv_path": str(target),
    }


@router.post("/url")
async def upload_url_endpoint(payload: dict) -> dict:
    """Ingest a remote URL (HTML/text)."""
    url = (payload or {}).get("url")
    if not url:
        raise HTTPException(400, "missing 'url'")
    try:
        stats = ingest_url(url)
    except Exception as exc:
        logger.exception("URL ingestion failed: {}", exc)
        raise HTTPException(500, f"ingestion failed: {exc}")
    get_query_cache().clear()
    get_retriever.cache_clear()  # type: ignore[attr-defined]
    return {"status": "ok", **stats}


@router.get("/sources")
async def list_sources() -> dict:
    return {
        "documents": list_uploads(),
        "allowed_extensions": sorted(ALLOWED_EXTS),
        "max_bytes": MAX_BYTES,
        "csv_path": str(get_settings().data_csv_path),
    }


@router.delete("/sources/{filename}")
async def remove_source(filename: str) -> dict:
    ok = delete_upload(filename)
    if not ok:
        raise HTTPException(404, "file not found")
    return {"status": "deleted", "name": filename}
