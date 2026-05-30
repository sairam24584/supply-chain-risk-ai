"""One-shot ingestion pipeline.

Usage (from the `backend/` directory):
    python -m scripts.ingest                # incremental upsert
    python -m scripts.ingest --rebuild      # drop collection first
    python -m scripts.ingest --local-embed  # force local SentenceTransformer
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `app.*` importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import logger, setup_logging  # noqa: E402
from app.services.chunking import chunk_records  # noqa: E402
from app.services.data_loader import build_incident_records, load_dataframe  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402
from app.services.vector_store import VectorStore  # noqa: E402


def run(rebuild: bool, force_local: bool) -> None:
    setup_logging()
    settings = get_settings()

    # Clear analytics caches so derived fields (incl. anomaly_score) refresh.
    from app.services import analytics, anomaly, intelligence
    analytics.get_df.cache_clear()
    anomaly.clear_cache()
    intelligence.clear_cache()

    logger.info("Loading CSV from {}", settings.data_csv_path)
    df = load_dataframe(settings.data_csv_path)
    logger.info("Loaded {} rows. Severity distribution:\n{}",
                len(df), df["risk_severity"].value_counts().to_dict())

    records = build_incident_records(df)
    chunks = chunk_records(records)
    logger.info("{} incident records -> {} chunks.", len(records), len(chunks))

    embedder = get_embedder(force_local=force_local)
    store = VectorStore(settings.chroma_persist_dir, embedder=embedder)
    if rebuild:
        store.reset()
    store.upsert(chunks)
    logger.info("Done. Collection size = {}", store.count())


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest supply chain CSV into Chroma.")
    parser.add_argument("--rebuild", action="store_true", help="Drop collection before ingesting.")
    parser.add_argument("--local-embed", action="store_true", help="Force local embedder.")
    args = parser.parse_args()
    run(rebuild=args.rebuild, force_local=args.local_embed)


if __name__ == "__main__":
    main()
