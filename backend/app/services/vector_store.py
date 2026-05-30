"""Chroma persistent vector store wrapper.

Encapsulates collection management, upsert, and similarity search with metadata
filtering. The embedder is injected so we can swap OpenAI / local without
touching this module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings
from app.core.logging import logger
from app.services.data_loader import IncidentRecord
from app.services.embeddings import Embedder, get_embedder

COLLECTION_NAME = "supply_chain_incidents"


class VectorStore:
    def __init__(self, persist_dir: Path, embedder: Embedder | None = None) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = embedder or get_embedder()
        logger.info(
            "VectorStore ready | dir={} | items={} | embedder={}",
            persist_dir,
            self._collection.count(),
            self._embedder.name,
        )

    # --- writes ---

    def upsert(self, records: list[IncidentRecord]) -> int:
        if not records:
            return 0
        texts = [r.text for r in records]
        embeddings = self._embedder.embed(texts)
        self._collection.upsert(
            ids=[r.doc_id for r in records],
            documents=texts,
            metadatas=[r.metadata for r in records],
            embeddings=embeddings,
        )
        logger.info("Upserted {} records into '{}'.", len(records), COLLECTION_NAME)
        return len(records)

    def reset(self) -> None:
        """Drop and recreate the collection (used by `ingest --rebuild`)."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("Collection '{}' reset.", COLLECTION_NAME)

    # --- reads ---

    def count(self) -> int:
        return self._collection.count()

    def similarity_search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return `top_k` semantically closest records, optionally filtered by metadata."""
        embedding = self._embedder.embed([query])[0]
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where or None,
        )
        hits: list[dict[str, Any]] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for i, doc_id in enumerate(ids):
            hits.append(
                {
                    "id": doc_id,
                    "text": docs[i] if i < len(docs) else "",
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": dists[i] if i < len(dists) else None,
                }
            )
        return hits


def get_vector_store(embedder: Embedder | None = None) -> VectorStore:
    """Module-level accessor using configured persist dir."""
    settings = get_settings()
    return VectorStore(settings.chroma_persist_dir, embedder=embedder)


__all__ = ["VectorStore", "get_vector_store", "COLLECTION_NAME"]
