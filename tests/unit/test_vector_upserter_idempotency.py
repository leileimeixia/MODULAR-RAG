"""Tests for idempotent vector-store upserts."""

from __future__ import annotations

import pytest

from core import ChunkRecord
from core.trace import TraceContext
from ingestion.storage import VectorUpserter, VectorUpserterError
from libs.vector_store import BaseVectorStore, VectorQueryResult, VectorRecord


class FakeVectorStore(BaseVectorStore):
    def __init__(self) -> None:
        self.records: dict[str, VectorRecord] = {}
        self.calls: list[list[VectorRecord]] = []

    def upsert(self, records: list[VectorRecord], trace=None) -> None:
        self.calls.append(records)
        for record in records:
            self.records[record.id] = record

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict | None = None,
        trace=None,
    ) -> list[VectorQueryResult]:
        return []

    def get_by_ids(self, ids: list[str], trace=None) -> list[VectorRecord]:
        return [self.records[record_id] for record_id in ids if record_id in self.records]


def _record(index: int, text: str | None = None) -> ChunkRecord:
    text = text if text is not None else f"chunk {index}"
    return ChunkRecord(
        id=f"chunk-{index}",
        text=text,
        metadata={"source_path": "docs/sample.md", "chunk_index": index},
        dense_vector=[float(index), float(len(text))],
        sparse_vector={text: 1.0} if text else {},
    )


def test_vector_upserter_uses_stable_chunk_ids_for_idempotency() -> None:
    store = FakeVectorStore()
    record = _record(0, "alpha")
    upserter = VectorUpserter(vector_store=store)

    first_ids = upserter.upsert([record])
    second_ids = upserter.upsert([record])

    assert first_ids == second_ids == ["chunk-0"]
    assert list(store.records) == ["chunk-0"]
    assert store.records["chunk-0"].text == "alpha"


def test_vector_upserter_replaces_existing_record_by_id() -> None:
    store = FakeVectorStore()
    upserter = VectorUpserter(vector_store=store)

    upserter.upsert([_record(0, "old")])
    upserter.upsert([_record(0, "new")])

    assert len(store.records) == 1
    assert store.records["chunk-0"].text == "new"
    assert store.records["chunk-0"].vector == [0.0, 3.0]


def test_vector_upserter_supports_batch_upsert_and_preserves_order() -> None:
    store = FakeVectorStore()
    records = [_record(index) for index in range(3)]

    ids = VectorUpserter(vector_store=store).upsert(records)

    assert ids == ["chunk-0", "chunk-1", "chunk-2"]
    assert [record.id for record in store.calls[0]] == ids


def test_vector_upserter_maps_text_vector_and_metadata() -> None:
    store = FakeVectorStore()

    VectorUpserter(vector_store=store).upsert([_record(1, "alpha")])

    vector_record = store.records["chunk-1"]
    assert vector_record.text == "alpha"
    assert vector_record.vector == [1.0, 5.0]
    assert vector_record.metadata == {
        "source_path": "docs/sample.md",
        "chunk_index": 1,
        "chunk_id": "chunk-1",
    }


def test_vector_upserter_returns_empty_for_empty_input() -> None:
    assert VectorUpserter(vector_store=FakeVectorStore()).upsert([]) == []


def test_vector_upserter_rejects_non_chunk_records() -> None:
    with pytest.raises(VectorUpserterError, match="ChunkRecord"):
        VectorUpserter(vector_store=FakeVectorStore()).upsert(["bad"])


def test_vector_upserter_rejects_records_without_dense_vector() -> None:
    record = ChunkRecord(
        id="chunk-0",
        text="alpha",
        metadata={"source_path": "docs/sample.md"},
        sparse_vector={"alpha": 1.0},
    )

    with pytest.raises(VectorUpserterError, match="dense_vector"):
        VectorUpserter(vector_store=FakeVectorStore()).upsert([record])


def test_vector_upserter_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-upsert")

    VectorUpserter(vector_store=FakeVectorStore()).upsert([_record(0)], trace=trace)

    assert trace.stages[-1].name == "vector_upsert"
    assert trace.stages[-1].method == "FakeVectorStore"
    assert trace.stages[-1].details == {"record_count": 1, "ids": ["chunk-0"]}
