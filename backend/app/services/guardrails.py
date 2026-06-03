"""Input and output guardrails for the supply-chain assistant."""
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

# Supply-chain vocabulary used for in-scope check.
_DOMAIN_VOCAB = {
    "supplier", "suppliers", "warehouse", "warehouses", "inventory", "stock",
    "shipment", "shipments", "shipping", "carrier", "carriers", "route", "routes",
    "delivery", "deliveries", "delay", "delays", "delayed", "logistics",
    "manufacturing", "production", "procurement", "vendor", "vendors",
    "sku", "skus", "defect", "defects", "inspection", "quality", "lead time",
    "order", "orders", "demand", "forecast", "freight", "transport",
    "stockout", "overstock", "risk", "disruption", "bottleneck", "fulfillment",
    "anomaly", "anomalies", "product", "products", "category", "categories",
    "location", "locations", "region", "regions", "department", "departments",
    "transportation", "data", "overview", "supply", "chain", "operations",
    "performance", "cost", "costs", "revenue", "price", "analysis",
    "mitigation", "mitigate", "recommend", "recommendation", "action", "plan",
    "reduce", "improve", "optimize", "resolve", "address", "fix",
    "issue", "issues", "problem", "problems", "concern", "concerns",
    "urgent", "critical", "status", "health", "situation", "summary",
    "overview", "today", "focus", "happening", "update", "alert", "alerts",
}

_MIN_DOMAIN_HITS = 1

_GENERAL_KNOWLEDGE_RE = re.compile(
    r"^\s*(what\s+is\s+(a\s+|an\s+|the\s+)?(?!our\b|my\b|the\s+current\b|this\b)"
    r"|define\s+|explain\s+(me\s+)?(what\s+is\s+)?"
    r"|tell\s+me\s+about\s+(a\s+|an\s+|the\s+concept\b)"
    r"|how\s+does\s+.{0,30}\s+work\b"
    r"|what\s+does\s+.{0,20}\s+mean\b)",
    re.IGNORECASE,
)

# Follow-up / contextual reference queries — short queries that refer back to
# a previous answer. These have no domain vocab but must reach LangGraph so the
# conversation memory (MemorySaver + thread_id) can resolve the reference.
_FOLLOWUP_RE = re.compile(
    r"^\s*("
    r"from\s+(the|that|this)\s+(list|above|earlier|previous|answer|response)"
    r"|who\s+is\s+(the\s+)?(top|best|worst|first|second|highest|lowest|most|least)"
    r"|which\s+(one|supplier|carrier|sku|product|is|has|have)"
    r"|tell\s+me\s+more(\s+about)?"
    r"|can\s+you\s+(elaborate|explain\s+more|expand)"
    r"|what\s+about\s+(the|that|this|them|it)"
    r"|and\s+(the|what\s+about)"
    r"|more\s+details?"
    r"|who\s+is\s+(the\s+)?top"
    r"|top\s+one"
    r"|the\s+(first|second|third|top|best|worst)"
    r"|elaborate(\s+on\s+(that|this|it))?"
    r"|go\s+on"
    r"|continue"
    r"|and\s+then"
    r")\b",
    re.IGNORECASE,
)

_ENTITY_REF_RE = re.compile(
    r"\b(for\s+[A-Z]|current\s+\w|this\s+(week|month|quarter)\b|SKU\d|[Ss]upplier\s+\d|"
    r"supplier|suppliers|inventory|shipment|shipments|carrier|carriers|"
    r"route|routes|defect|stockout|overstock|delay|delays|sku|skus|"
    r"risk|quality|logistics|supply\s+chain|warehouse|procurement|"
    r"freight|transport|fulfillment|anomaly|disruption)\b",
    re.I,
)


@dataclass
class GuardResult:
    ok: bool
    value: str
    violations: list[str] = field(default_factory=list)


def _redact(text: str) -> tuple[str, list[str]]:
    """Mask emails, phones, card-like numbers, API keys."""
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

    # PII strip (allow through, but redacted)
    q, pii_hits = _redact(q)
    violations.extend(pii_hits)

    # Follow-up / conversational reference queries bypass scope check entirely.
    # These are short queries referring to a previous answer ("from the list who
    # is the top?", "tell me more", "which one?"). LangGraph resolves them via
    # conversation memory (MemorySaver + thread_id).
    if _FOLLOWUP_RE.match(q):
        return GuardResult(ok=True, value=q, violations=violations)

    # Block pure general-knowledge queries unless they reference operational entities.
    if _GENERAL_KNOWLEDGE_RE.match(q) and not _ENTITY_REF_RE.search(q):
        violations.append("out_of_scope")

    # In-scope check: must contain at least one supply-chain domain word.
    if "out_of_scope" not in violations:
        words = set(lower.split())
        domain_hits = words & _DOMAIN_VOCAB
        if not domain_hits:
            violations.append("out_of_scope")

    ok = not any(v in ("prompt_injection", "out_of_scope") for v in violations)
    return GuardResult(ok=ok, value=q, violations=violations)



def check_output(
    answer: str,
    allowed_suppliers: set[str] | None = None,
    allowed_skus: set[str] | None = None,
    allowed_sources: set[str] | None = None,
    citations: list[str] | None = None,
) -> GuardResult:
    """Validate / sanitise LLM output."""
    violations: list[str] = []

    if not answer or not answer.strip():
        return GuardResult(ok=False, value="", violations=["empty_output"])

    # Redact PII that may have leaked into the answer
    clean, pii_hits = _redact(answer)
    violations.extend(pii_hits)

    # Hallucinated entity check (soft — logged but non-blocking)
    if allowed_suppliers:
        for m in re.finditer(r"\bSupplier\s+(\w+)\b", clean, re.IGNORECASE):
            name = "Supplier %s" % m.group(1)
            if name not in allowed_suppliers:
                violations.append("hallucinated_entity:%s" % name)

    if allowed_skus:
        for m in re.finditer(r"\bSKU(\d+)\b", clean, re.IGNORECASE):
            sku = "SKU%s" % m.group(1)
            if sku not in allowed_skus:
                violations.append("hallucinated_sku:%s" % sku)

    # Only hard-fail on empty output (handled above); everything else is a warning.
    return GuardResult(ok=True, value=clean, violations=violations)


__all__ = ["GuardResult", "check_input", "check_output"]
