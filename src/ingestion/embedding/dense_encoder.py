"""Dense embedding encoder for ingestion chunks."""

from __future__ import annotations

from typing import Any

from core import Chunk, ChunkRecord
from libs.embedding import BaseEmbedding, EmbeddingFactory


class DenseEncoderError(ValueError):
    """Raised when dense encoding cannot produce valid vectors."""


class DenseEncoder:
    """Encode chunk text into dense vectors and return ChunkRecord objects."""

    def __init__(
        self,
        settings: Any | None = None,
        embedding: BaseEmbedding | None = None,
    ) -> None:
        self.settings = settings
        self.embedding = embedding or EmbeddingFactory.create(settings)

    def encode(self, chunks: list[Chunk], trace: Any | None = None) -> list[ChunkRecord]:
        """Encode chunks in order and attach vectors to ChunkRecord payloads."""
        if not chunks:
            return []
        if not all(isinstance(chunk, Chunk) for chunk in chunks):
            raise DenseEncoderError("DenseEncoder.encode expects a list of Chunk objects")

        texts = [chunk.text for chunk in chunks]
        vectors = self.embedding.embed(texts, trace=trace)
        _validate_vectors(chunks, vectors)

        records = [
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=chunk.metadata,
                dense_vector=[float(value) for value in vector],
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if trace is not None:
            trace.record_stage(
                "dense_encoding",
                method=self.embedding.__class__.__name__,
                details={"chunk_count": len(records), "dimensions": len(records[0].dense_vector or [])},
            )
        return records


def _validate_vectors(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    if len(vectors) != len(chunks):
        raise DenseEncoderError(
            f"embedding returned {len(vectors)} vectors for {len(chunks)} chunks"
        )
    if not vectors:
        return
    dimensions = len(vectors[0])
    if dimensions <= 0:
        raise DenseEncoderError("embedding returned an empty dense vector")
    for index, vector in enumerate(vectors):
        if len(vector) != dimensions:
            raise DenseEncoderError("embedding returned inconsistent vector dimensions")
        if not all(isinstance(value, int | float) for value in vector):
            raise DenseEncoderError(f"embedding vector at index {index} contains non-numeric values")
