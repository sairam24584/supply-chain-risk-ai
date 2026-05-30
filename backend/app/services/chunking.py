"""Recursive semantic chunking for incident narratives.

Wraps LangChain's RecursiveCharacterTextSplitter with project defaults. Each chunk
keeps the source incident's metadata so retrieval can filter on it.
"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.data_loader import IncidentRecord

DEFAULT_CHUNK_SIZE = 600
DEFAULT_CHUNK_OVERLAP = 80


def chunk_records(
    records: list[IncidentRecord],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IncidentRecord]:
    """Split each incident narrative into 1+ semantic chunks, preserving metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunked: list[IncidentRecord] = []
    for rec in records:
        pieces = splitter.split_text(rec.text)
        if len(pieces) == 1:
            chunked.append(rec)
            continue
        for i, piece in enumerate(pieces):
            chunked.append(
                IncidentRecord(
                    doc_id=f"{rec.doc_id}-chunk-{i}",
                    text=piece,
                    metadata={**rec.metadata, "chunk_index": i, "parent_id": rec.doc_id},
                )
            )
    return chunked


__all__ = ["chunk_records", "DEFAULT_CHUNK_SIZE", "DEFAULT_CHUNK_OVERLAP"]
