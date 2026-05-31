"""Input and output guardrails for the supply-chain assistant.

Inputs:
  * length sanity (already done by pydantic, we re-check)
  * prompt-injection patterns (ignore previous, system override, jailbreak)
  * PII redaction (emails, phones, credit-card-like strings)
  * in-scope check (must reference a supply-chain concept — heuristic, not LLM)

Outputs:
  * cited entity check (LLM must not invent supplier/SKU names absent from retrieved context)
  * PII redaction on the final answer
  * fail-soft: returns a sanitised string + a list of violations, never raises mid-graph
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- patterns ---

_PROMPT_INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?previous\s+instructions\b",
    r"\bdisregard\s+the\s+system\b",
    r"\bsystem\s+prompt\b",
    r"\bjailbreak\b",
    r"\bact\s+as\s+(an?\s+)?different\s+(ai|model)\b",
    r"\breveal\s+your\s+prompt\b",
]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s\-]?)?\(?\d{3,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,5}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_API_KEY_RE = re.compile(r"\b(sk-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|ls__[A-Za-z0-9]{20,})\b")

# Supply-chain vocabulary used for in-scope check. Heuristic — keep broad.
_DOMAIN_VOCAB = {
    "supplier", "suppliers", "warehouse", "warehouses", "inventory", "stock",
    "shipment", "shipments", "shipping", "carrier", "carriers", "route", "routes",
    "delivery", "deliveries", "delay", "delays", "delayed", "logistics",
    "manufacturing", "production", "procurement", "vendor", "vendors",
    "sku", "skus", "defect", "defects", "inspection", "quality", "lead time",
    "order", "orders", "demand", "forecast", "freight", "transport",
    "stockout", "overstock", "risk", "disruption", "bottleneck", "fulfillment",
    # broader data-query terms
    "anomaly", "anomalies", "product", "products", "category", "categories",
    "location", "locations", "region", "regions", "department", "departments",
    "transportation", "data", "overview", "supply", "chain", "operations",
    "performance", "cost", "costs", "revenue", "price", "analysis",
}

# Threshold below which we consider the query likely out-of-scope.
_MIN_DOMAIN_HITS = 1

# "What is X" / "Define X" / "Explain X" patterns that are general knowledge
# questions, not operational data queries — block even if domain words appear.
_GENERAL_KNOWLEDGE_RE = re.compile(
    r"^\s*(what\s+is\s+(a\s+|an\s+|the\s+)?(?!our\b|my\b|the\s+current\b|this\b)"
    r"|define\s+|explain\s+(me\s+)?(what\s+is\s+)?"
    r"|tell\s+me\s+about\s+(a\s+|an\s+|the\s+concept\b)"
    r"|how\s+does\s+.{0,30}\s+work\b"
    r"|what\s+does\s+.{0,20}\s+mean\b)",
    re.IGNORECASE,
)


@dataclass
class GuardResult:
    ok: bool
    value: str
    violations: list[str] = field(default_factory=list)


def _redact(text: str) -> tuple[str, list[str]]:
    """Mask emails, phones, card-like numbers, API keys. Returns (clean, hits)."""
    hits: list[str] = []
    redacted = text
    for label, rgx, mask in [
        ("email", _EMAIL_RE, "[REDACTED_EMAIL]"),
        ("phone", _PHONE_RE, "[REDACTED_PHONE]"),
        ("card", _CC_RE, "[REDACTED_CARD]"),
        ("api_key", _API_KEY_RE, "[REDACTED_KEY]"),
    ]:
        if rgx.search(redacted):
            redacted = rgx.sub(mask, redacted)
            hits.append(f"pii:{label}")
    return redacted, hits


def check_input(query: str) -> GuardResult:
    """Validate an incoming user query."""
    violations: list[str] = []

    q = query.strip()
    if not q:
        return GuardResult(ok=False, value=q, violations=["empty_query"])
    if len(q) > 1000:
        return GuardResult(ok=False, value=q, violations=["query_too_long"])

    lower = q.lower()
    for pat in _PROMPT_INJECTION_PATTERNS:
        if re.search(pat, lower):
            violations.append("prompt_injection")
            break

    # PII strip (still allow query through, but redacted)
    q, pii_hits = _redact(q)
    violations.extend(pii_hits)

    # Block "what is supply and demand" style general-knowledge definitions,
    # but allow operational queries that reference specific entities ("for Supplier X",
    # "for SKU", "our", "my", "this week", etc.)
    _ENTITY_REF_RE = re.compile(
        r"\b(for\s+[A-Z]|our\b|my\b|this\b|current\b|SKU\d|[Ss]upplier\s+\d)", re.I
    )
    if _GENERAL_KNOWLEDGE_RE.match(q) and not _ENTITY_REF_RE.search(q):
        violations.append("out_of_scope")

    # In-scope check (only if not already blocked)
    if "out_of_scope" not in violations:
        tokens = set(re.findall(r"[A-Za-z]+", lower))
        domain_hits = sum(1 for w in _DOMAIN_VOCAB if w in lower or w in tokens)
        if domain_hits < _MIN_DOMAIN_HITS:
            violations.append("out_of_scope")

    # Hard fails: injection + out_of_scope are reject reasons.
    ok = "prompt_injection" not in violations and "out_of_scope" not in violations
    return GuardResult(ok=ok, value=q, violations=violations)


def check_output(
    answer: str,
    allowed_suppliers: set[str],
    allowed_skus: set[str],
    allowed_sources: set[str] | None = None,
    citations: list[str] | None = None,
    original_query: str | None = None,
) -> GuardResult:
    """Validate the agent's final answer."""
    if not answer:
        return GuardResult(ok=False, value="", violations=["empty_output"])

    violations: list[str] = []

    for m in re.findall(r"\bSupplier\s+\d+\b", answer):
        if m not in allowed_suppliers:
            violations.append(f"hallucinated_supplier:{m}")
    for m in re.findall(r"\bSKU\d+\b", answer):
        if m not in allowed_skus:
            violations.append(f"hallucinated_sku:{m}")

    if citations:
        valid_pool = set(allowed_skus) | (allowed_sources or set()) | allowed_suppliers
        for c in citations:
            if not c:
                continue
            if c not in valid_pool:
                violations.append(f"unverifiable_citation:{c}")

    cleaned, pii_hits = _redact(answer)
    violations.extend(pii_hits)

    return GuardResult(ok=True, value=cleaned, violations=violations)


__all__ = ["GuardResult", "check_input", "check_output"]
