"""Batch orchestration for dense and sparse chunk encoding."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from core import Chunk, ChunkRecord

from .dense_encoder import DenseEncoder
from .sparse_encoder import SparseEncoder


class BatchProcessorError(ValueError):
    """Raised when batch encoding cannot produce aligned records."""


class BatchProcessor:
    """Split chunks into batches and combine dense/sparse encoder outputs."""

    def __init__(
        self,
        batch_size: int = 32,
        settings: Any | None = None,
        dense_encoder: Any | None = None,
        sparse_encoder: Any | None = None,
    ) -> None:
        if batch_size <= 0:
            raise BatchProcessorError("batch_size must be greater than 0")
        self.batch_size = batch_size
        self.dense_encoder = dense_encoder or DenseEncoder(settings=settings)
        self.sparse_encoder = sparse_encoder or SparseEncoder()

    def process(self, chunks: list[Chunk], trace: Any | None = None) -> list[ChunkRecord]:
        """Encode chunks in stable batch order and return combined records."""
        if not chunks:
            return []
        if not all(isinstance(chunk, Chunk) for chunk in chunks):
            raise BatchProcessorError("BatchProcessor.process expects a list of Chunk objects")

        all_records: list[ChunkRecord] = []
        batch_details: list[dict[str, int | float]] = []
        for batch_index, batch in enumerate(_batches(chunks, self.batch_size)):
            started_at = perf_counter()
            dense_records = self.dense_encoder.encode(batch, trace=trace)
            sparse_records = self.sparse_encoder.encode(batch, trace=trace)
            all_records.extend(_merge_records(batch, dense_records, sparse_records))
            batch_details.append(
                {
                    "index": batch_index,
                    "chunk_count": len(batch),
                    "elapsed_seconds": round(perf_counter() - started_at, 6),
                }
            )

        if trace is not None:
            trace.record_stage(
                "batch_processing",
                method="dense_sparse",
                details={
                    "chunk_count": len(chunks),
                    "batch_size": self.batch_size,
                    "batch_count": len(batch_details),
                    "batches": batch_details,
                },
            )
        return all_records


def _batches(chunks: list[Chunk], batch_size: int) -> list[list[Chunk]]:
    return [chunks[index : index + batch_size] for index in range(0, len(chunks), batch_size)]


def _merge_records(
    batch: list[Chunk],
    dense_records: list[ChunkRecord],
    sparse_records: list[ChunkRecord],
) -> list[ChunkRecord]:
    if len(dense_records) != len(batch):
        raise BatchProcessorError(
            f"dense encoder returned {len(dense_records)} records for {len(batch)} chunks"
        )
    if len(sparse_records) != len(batch):
        raise BatchProcessorError(
            f"sparse encoder returned {len(sparse_records)} records for {len(batch)} chunks"
        )

    merged: list[ChunkRecord] = []
    for chunk, dense_record, sparse_record in zip(batch, dense_records, sparse_records, strict=True):
        if dense_record.id != chunk.id or sparse_record.id != chunk.id:
            raise BatchProcessorError("encoder records must preserve chunk ids and order")
        merged.append(
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=chunk.metadata,
                dense_vector=dense_record.dense_vector,
                sparse_vector=sparse_record.sparse_vector,
            )
        )
    return merged
