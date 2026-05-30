"""User-uploaded document ingestion (multi-format).

Pipeline:  save  →  load (format-aware)  →  preprocess (clean + enrich)
        →  chunk (recursive semantic)  →  embed  →  Chroma upsert.

Adds rich, per-segment metadata (source_file, page_number, sheet, mime,
categories, dates_mentioned, pii_flags) so retrieval can filter precisely.
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import logger
from app.services.chunking import chunk_records
from app.services.data_loader import IncidentRecord
from app.services.document_loaders import ALLOWED_EXTS, load_any, load_url
from app.services.document_preprocessor import preprocess
from app.services.vector_store import get_vector_store

UPLOAD_DIR = get_settings().chroma_persist_dir.parent / "uploads"
MAX_BYTES = 25 * 1024 * 1024   # 25 MB now that we support docx/xlsx


def _ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def _safe_filename(name: str) -> str:
    base = Path(name).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base) or "file"


def save_upload(filename: str, blob: bytes) -> Path:
    if len(blob) > MAX_BYTES:
        raise ValueError(f"file too large: {len(blob)} > {MAX_BYTES} bytes")
    safe = _safe_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"unsupported extension: {ext}. Allowed: {sorted(ALLOWED_EXTS)}")
    _ensure_upload_dir()
    target = UPLOAD_DIR / safe
    target.write_bytes(blob)
    logger.info("Saved upload: {} ({} bytes)", target.name, len(blob))
    return target


def _build_records(prepared_segments, file_id: str, source_label: str) -> list[IncidentRecord]:
    """Turn cleaned segments into IncidentRecords (one per loader-segment, then chunked)."""
    parents: list[IncidentRecord] = []
    for i, seg in enumerate(prepared_segments):
        sub_id = seg.metadata.get("page_number") or seg.metadata.get("sheet") or i + 1
        parents.append(
            IncidentRecord(
                doc_id=f"userdoc-{file_id}-{sub_id}",
                text=seg.text,
                metadata={
                    **seg.metadata,
                    "doc_type": "user_doc",
                    "source_label": source_label,
                    "ingested_at": int(time.time()),
                    # Defaults so existing metadata filters keep working
                    "supplier": seg.metadata.get("supplier") or "n/a",
                    "location": seg.metadata.get("location") or "n/a",
                    "risk_severity": seg.metadata.get("risk_severity") or "n/a",
                },
            )
        )
    return parents


def ingest_document(path: Path) -> dict[str, Any]:
    """Load → preprocess → chunk → embed → upsert. Returns stats."""
    raw_segments = load_any(path)
    if not raw_segments:
        raise ValueError("loader returned no segments")
    prepared = preprocess(raw_segments)

    file_id = hashlib.sha1(path.name.encode()).hexdigest()[:10]
    parents = _build_records(prepared, file_id, source_label=path.name)
    chunks = chunk_records(parents)

    store = get_vector_store()
    n = store.upsert(chunks)
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "loader": prepared[0].metadata.get("loader", "?"),
        "segments": len(prepared),
        "chunks": len(chunks),
        "upserted": n,
        "doc_ids": [r.doc_id for r in parents][:10],
        "categories_detected": sorted({c for s in prepared for c in s.metadata.get("categories", [])}),
    }


def ingest_url(url: str) -> dict[str, Any]:
    raw_segments = load_url(url)
    prepared = preprocess(raw_segments)
    file_id = hashlib.sha1(url.encode()).hexdigest()[:10]
    parents = _build_records(prepared, file_id, source_label=url)
    chunks = chunk_records(parents)
    store = get_vector_store()
    n = store.upsert(chunks)
    return {
        "url": url,
        "loader": prepared[0].metadata.get("loader", "?"),
        "segments": len(prepared),
        "chunks": len(chunks),
        "upserted": n,
    }


def list_uploads() -> list[dict[str, Any]]:
    if not UPLOAD_DIR.exists():
        return []
    out = []
    for p in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        out.append({
            "name": p.name,
            "ext":  p.suffix.lower(),
            "bytes": p.stat().st_size,
            "modified": int(p.stat().st_mtime),
        })
    return out


def delete_upload(filename: str) -> bool:
    safe = _safe_filename(filename)
    target = UPLOAD_DIR / safe
    if not target.exists() or not target.is_file():
        return False
    target.unlink()
    logger.info("Deleted upload: {}", target.name)
    return True


__all__ = [
    "ALLOWED_EXTS", "MAX_BYTES", "UPLOAD_DIR",
    "save_upload", "ingest_document", "ingest_url",
    "list_uploads", "delete_upload",
]
