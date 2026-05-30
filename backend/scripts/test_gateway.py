"""Standalone gateway smoke test.

Probes the OpenAI-compatible gateway for:
  1. Chat completions  (gpt-4o-mini)
  2. Single embedding  (text-embedding-3-small)
  3. Batch embeddings  (3 inputs)

Usage (from project root):
    python backend/scripts/test_gateway.py

Reports PASS/FAIL per test so we know whether the gateway supports
both chat AND embeddings before running the full ingest.
"""
from __future__ import annotations

import sys

GATEWAY = "https://keygateway.arshnivlabs.com/v1"
KEY = "learner001"


def _print_header(n: int, label: str) -> None:
    print("=" * 60)
    print(f"TEST {n}: {label}")
    print("=" * 60)


def main() -> int:
    try:
        from openai import OpenAI
    except ImportError:
        print("openai package not installed. Run: pip install openai")
        return 1

    client = OpenAI(api_key=KEY, base_url=GATEWAY)
    failures: list[str] = []

    # --- chat ---
    _print_header(1, "Chat completions (gpt-4o-mini)")
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Reply with exactly: PING_OK"}],
            max_tokens=10,
            temperature=0,
        )
        print("status: PASS")
        print("model :", r.model)
        print("reply :", r.choices[0].message.content)
        print("usage :", r.usage)
    except Exception as e:
        print("status: FAIL")
        print("error :", type(e).__name__, str(e)[:400])
        failures.append("chat")

    print()

    # --- single embedding ---
    _print_header(2, "Single embedding (text-embedding-3-small)")
    try:
        r = client.embeddings.create(
            model="text-embedding-3-small",
            input=["supply chain risk test"],
        )
        vec = r.data[0].embedding
        print("status: PASS")
        print("model :", r.model)
        print("dims  :", len(vec))
        print("first5:", [round(x, 4) for x in vec[:5]])
        print("usage :", r.usage)
    except Exception as e:
        print("status: FAIL")
        print("error :", type(e).__name__, str(e)[:400])
        failures.append("embedding-single")

    print()

    # --- batch embeddings ---
    _print_header(3, "Batch embeddings (3 inputs)")
    try:
        r = client.embeddings.create(
            model="text-embedding-3-small",
            input=["supplier risk", "shipment delay", "stockout warning"],
        )
        print("status: PASS")
        print("count :", len(r.data))
        print("dims  :", len(r.data[0].embedding))
    except Exception as e:
        print("status: FAIL")
        print("error :", type(e).__name__, str(e)[:400])
        failures.append("embedding-batch")

    print()
    print("=" * 60)
    if not failures:
        print("ALL TESTS PASSED - gateway supports chat + embeddings.")
        print("You can run the normal ingest:")
        print("  python -m scripts.ingest --rebuild")
        return 0
    else:
        print(f"FAILED: {', '.join(failures)}")
        if "chat" in failures:
            print("Chat is broken - gateway/key issue. Cannot proceed.")
        elif any(f.startswith("embedding") for f in failures):
            print("Embeddings unsupported on the gateway. Fix options:")
            print("  1. Use local embedder for ingestion:")
            print("     python -m scripts.ingest --rebuild --local-embed")
            print("  2. Ask the team to wire embeddings on the gateway")
        return 1


if __name__ == "__main__":
    sys.exit(main())
