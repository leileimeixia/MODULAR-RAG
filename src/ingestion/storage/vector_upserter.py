"""Idempotent vector-store upsert for encoded chunk records."""

from __future__ import annotations

from typing import Any

from core import ChunkRecord
from libs.vector_store import BaseVectorStore, VectorRecord, VectorStoreFactory


class VectorUpserterError(ValueError):
    """Raised when encoded chunk records cannot be upserted."""


class VectorUpserter:
    """Convert dense ChunkRecord payloads to VectorRecord objects and upsert them."""

    def __init__(
        self,
        settings: Any | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        self.settings = settings
        self.vector_store = vector_store or VectorStoreFactory.create(settings)

    def upsert(self, records: list[ChunkRecord], trace: Any | None = None) -> list[str]:
        """Upsert records into the vector store and return stable ids in input order."""
        if not records:
            return []
        if not all(isinstance(record, ChunkRecord) for record in records):
            raise VectorUpserterError("VectorUpserter.upsert expects ChunkRecord objects")

        vector_records = [_to_vector_record(record) for record in records]
        self.vector_store.upsert(vector_records, trace=trace)
        if trace is not None:
            trace.record_stage(
                "vector_upsert",
                method=self.vector_store.__class__.__name__,
                details={
                    "record_count": len(vector_records),
                    "ids": [record.id for record in vector_records],
                },
            )
        return [record.id for record in vector_records]


def _to_vector_record(record: ChunkRecord) -> VectorRecord:
    if record.dense_vector is None:
        raise VectorUpserterError(f"ChunkRecord {record.id} does not include dense_vector")
    return VectorRecord(
        id=record.id,
        text=record.text,
        vector=[float(value) for value in record.dense_vector],
        metadata={**record.metadata, "chunk_id": record.id},
    )
