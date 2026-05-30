"""Document preprocessing — clean, normalise, extract metadata, validate.

Sits between the loader and the chunker. Produces a list of `PreparedSegment`s
(text + enriched metadata) ready to be chunked & embedded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Heuristic patterns
_WHITESPACE_RE = re.compile(r"[ \t ]+")
_REPEATED_NEWLINES_RE = re.compile(r"\n{3,}")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PII_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PII_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s\-]?)?\(?\d{3,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,5}\b")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2})\b")

# Operational keywords used for cheap metadata enrichment
_DOMAIN_KEYWORDS = {
    "supplier":   ["supplier", "vendor", "manufacturer"],
    "shipment":   ["shipment", "shipping", "freight", "carrier", "route", "transit"],
    "inventory":  ["inventory", "stock", "stockout", "overstock", "warehouse"],
    "quality":    ["defect", "inspection", "quality", "fail", "recall"],
    "compliance": ["compliance", "regulation", "policy", "certification", "audit"],
    "contract":   ["contract", "agreement", "clause", "amendment", "sla"],
    "incident":   ["incident", "disruption", "outage", "delay", "issue"],
}

MIN_TEXT_LEN = 20         # docs shorter than this are useless
MAX_TEXT_LEN = 2_000_000  # 2 MB of raw text — guard against runaway uploads


@dataclass
class PreparedSegment:
    """One cleaned, validated, metadata-enriched piece of document text."""
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _clean(text: str) -> str:
    text = _CONTROL_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _REPEATED_NEWLINES_RE.sub("\n\n", text)
    return text.strip()


def _redact(text: str) -> tuple[str, list[str]]:
    """Mask emails + phones in document body so they don't leak through retrieval."""
    flags: list[str] = []
    if _PII_EMAIL_RE.search(text):
        text = _PII_EMAIL_RE.sub("[REDACTED_EMAIL]", text)
        flags.append("redacted_email")
    if _PII_PHONE_RE.search(text):
        text = _PII_PHONE_RE.sub("[REDACTED_PHONE]", text)
        flags.append("redacted_phone")
    return text, flags


def _detect_categories(text: str) -> list[str]:
    lower = text.lower()
    cats: list[str] = []
    for cat, keywords in _DOMAIN_KEYWORDS.items():
        if any(k in lower for k in keywords):
            cats.append(cat)
    return cats


def _detect_dates(text: str, limit: int = 3) -> list[str]:
    seen, out = set(), []
    for m in _DATE_RE.finditer(text):
        d = m.group(0)
        if d not in seen:
            seen.add(d)
            out.append(d)
            if len(out) >= limit:
                break
    return out


def preprocess(
    segments: list[tuple[str, dict[str, Any]]],
    extra_metadata: dict[str, Any] | None = None,
) -> list[PreparedSegment]:
    """Apply cleaning + redaction + metadata enrichment to a loader's output.

    Drops segments shorter than MIN_TEXT_LEN; clamps total length per segment.
    Raises ValueError if the entire batch yields nothing useful.
    """
    prepared: list[PreparedSegment] = []
    for raw_text, raw_meta in segments:
        if not raw_text:
            continue
        cleaned = _clean(raw_text)
        if len(cleaned) < MIN_TEXT_LEN:
            continue
        if len(cleaned) > MAX_TEXT_LEN:
            cleaned = cleaned[:MAX_TEXT_LEN]

        cleaned, pii_flags = _redact(cleaned)
        categories = _detect_categories(cleaned)
        dates = _detect_dates(cleaned)

        meta = {
            **(raw_meta or {}),
            **(extra_metadata or {}),
            "char_count": len(cleaned),
            "categories": categories,
            "dates_mentioned": dates,
        }
        if pii_flags:
            meta["pii_flags"] = pii_flags
        prepared.append(PreparedSegment(text=cleaned, metadata=meta))

    if not prepared:
        raise ValueError("preprocessing yielded no usable segments")
    return prepared


__all__ = ["PreparedSegment", "preprocess", "MIN_TEXT_LEN", "MAX_TEXT_LEN"]
