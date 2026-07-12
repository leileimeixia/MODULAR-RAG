"""Sparse term-frequency encoder for ingestion chunks."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from core import Chunk, ChunkRecord


class SparseEncoderError(ValueError):
    """Raised when sparse encoding cannot produce valid records."""


class SparseEncoder:
    """Encode chunk text into sparse term-frequency vectors for BM25 indexing."""

    def encode(self, chunks: list[Chunk], trace: Any | None = None) -> list[ChunkRecord]:
        """Encode chunks in order and attach term frequencies to ChunkRecord payloads."""
        if not chunks:
            return []
        if not all(isinstance(chunk, Chunk) for chunk in chunks):
            raise SparseEncoderError("SparseEncoder.encode expects a list of Chunk objects")

        records = [
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=chunk.metadata,
                sparse_vector=_term_frequencies(chunk.text),
            )
            for chunk in chunks
        ]
        if trace is not None:
            trace.record_stage(
                "sparse_encoding",
                method="term_frequency",
                details={
                    "chunk_count": len(records),
                    "total_terms": sum(
                        int(sum(record.sparse_vector.values()))
                        for record in records
                        if record.sparse_vector is not None
                    ),
                    "empty_chunks": sum(1 for record in records if not record.sparse_vector),
                },
            )
        return records


def _term_frequencies(text: str) -> dict[str, float]:
    terms = _tokenize(text)
    return {term: float(count) for term, count in Counter(terms).items()}


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in re.finditer(r"\w+", text)]
