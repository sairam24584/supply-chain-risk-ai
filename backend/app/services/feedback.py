"""User feedback loop.

Stores thumbs-up / thumbs-down votes in SQLite (data/feedback.db).
The retriever calls `get_boost_map()` to apply a small multiplicative
boost to document RRF scores for positively-rated queries.

Schema:
  feedback(id, created_at, query_hash, query_text, doc_id, vote, session_id)
  vote: +1 (thumbs up) | -1 (thumbs down)
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import logger

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "feedback.db"

# Score multiplier applied to doc RRF score when it has net positive feedback
POSITIVE_BOOST = 1.25
NEGATIVE_PENALTY = 0.80


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]


def _ensure_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                query_hash  TEXT    NOT NULL,
                query_text  TEXT    NOT NULL,
                doc_id      TEXT,
                vote        INTEGER NOT NULL,  -- +1 or -1
                session_id  TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_qhash ON feedback(query_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_doc   ON feedback(doc_id)")


@contextmanager
def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Public write API ──────────────────────────────────────────────────────────

def record_feedback(
    query: str,
    vote: int,
    doc_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Store one feedback record. vote must be +1 or -1."""
    if vote not in (1, -1):
        raise ValueError("vote must be +1 or -1")
    _ensure_db()
    with _get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO feedback (created_at, query_hash, query_text, doc_id, vote, session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                _query_hash(query),
                query,
                doc_id,
                vote,
                session_id,
            ),
        )
        row_id = cursor.lastrowid
    label = "thumbs_up" if vote == 1 else "thumbs_down"
    logger.info("Feedback recorded | id={} query='{}' vote={} doc={}", row_id, query[:60], label, doc_id)
    return {"id": row_id, "vote": vote, "label": label}


# ── Retrieval reweighting ─────────────────────────────────────────────────────

def get_boost_map() -> dict[str, float]:
    """Return {doc_id: multiplier} for all docs that have net feedback.

    Called by the retriever to adjust RRF scores before returning results.
    Docs with net_positive > 0  → POSITIVE_BOOST
    Docs with net_positive < 0  → NEGATIVE_PENALTY
    """
    _ensure_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT doc_id, SUM(vote) as net FROM feedback WHERE doc_id IS NOT NULL GROUP BY doc_id"
        ).fetchall()
    boost: dict[str, float] = {}
    for row in rows:
        net = row["net"]
        if net > 0:
            boost[row["doc_id"]] = POSITIVE_BOOST
        elif net < 0:
            boost[row["doc_id"]] = NEGATIVE_PENALTY
    return boost


def apply_feedback_boost(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Multiply rrf_score by the feedback multiplier, then re-sort."""
    boost_map = get_boost_map()
    if not boost_map:
        return hits
    for hit in hits:
        multiplier = boost_map.get(hit.get("id", ""), 1.0)
        if multiplier != 1.0:
            hit["rrf_score"] = round(hit.get("rrf_score", 0.0) * multiplier, 6)
            hit["feedback_boost"] = multiplier
    return sorted(hits, key=lambda h: h.get("rrf_score", 0.0), reverse=True)


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_feedback_stats() -> dict[str, Any]:
    _ensure_db()
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        ups = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote = 1").fetchone()[0]
        downs = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote = -1").fetchone()[0]
        top_docs = conn.execute(
            """SELECT doc_id, SUM(vote) as net, COUNT(*) as votes
               FROM feedback WHERE doc_id IS NOT NULL
               GROUP BY doc_id ORDER BY net DESC LIMIT 10"""
        ).fetchall()
    return {
        "total_votes": total,
        "thumbs_up": ups,
        "thumbs_down": downs,
        "top_docs": [dict(r) for r in top_docs],
    }
