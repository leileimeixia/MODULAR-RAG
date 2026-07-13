"""Roundtrip tests for the default ChromaStore adapter."""

from __future__ import annotations

import pytest

from core.settings import VectorStoreSettings
from libs.vector_store import (
    ChromaStore,
    ChromaStoreError,
    VectorQueryResult,
    VectorRecord,
    VectorStoreFactory,
)


def _settings(tmp_path, collection: str = "test_collection") -> VectorStoreSettings:
    return VectorStoreSettings(
        provider="chroma",
        persist_directory=str(tmp_path),
        collection_name=collection,
    )


def test_factory_creates_chroma_store(tmp_path) -> None:
    store = VectorStoreFactory.create(_settings(tmp_path))

    assert isinstance(store, ChromaStore)


def test_upsert_query_roundtrip_with_top_k_and_filters(tmp_path) -> None:
    store = ChromaStore(_settings(tmp_path))
    store.upsert(
        [
            VectorRecord(
                id="doc-a",
                text="alpha content",
                vector=[1.0, 0.0, 0.0],
                metadata={"collection": "docs", "source": "a.md"},
            ),
            VectorRecord(
                id="doc-b",
                text="beta content",
                vector=[0.8, 0.2, 0.0],
                metadata={"collection": "docs", "source": "b.md"},
            ),
            VectorRecord(
                id="other",
                text="other content",
                vector=[0.0, 1.0, 0.0],
                metadata={"collection": "other", "source": "c.md"},
            ),
        ]
    )

    results = store.query(
        [1.0, 0.0, 0.0],
        top_k=2,
        filters={"collection": "docs"},
    )

    assert results == [
        VectorQueryResult(
            id="doc-a",
            text="alpha content",
            score=1.0,
            metadata={"collection": "docs", "source": "a.md"},
        ),
        VectorQueryResult(
            id="doc-b",
            text="beta content",
            score=pytest.approx(0.9701425001453318),
            metadata={"collection": "docs", "source": "b.md"},
        ),
    ]


def test_upsert_replaces_existing_record(tmp_path) -> None:
    store = ChromaStore(_settings(tmp_path))
    store.upsert([VectorRecord(id="a", text="old", vector=[1.0], metadata={})])
    store.upsert([VectorRecord(id="a", text="new", vector=[2.0], metadata={})])

    results = store.query([1.0], top_k=5)

    assert len(results) == 1
    assert results[0].text == "new"


def test_records_persist_across_store_instances(tmp_path) -> None:
    settings = _settings(tmp_path)
    first = ChromaStore(settings)
    first.upsert(
        [
            VectorRecord(
                id="persisted",
                text="stored text",
                vector=[0.0, 1.0],
                metadata={"source": "persisted.md"},
            )
        ]
    )

    second = ChromaStore(settings)

    assert second.query([0.0, 1.0], top_k=1) == [
        VectorQueryResult(
            id="persisted",
            text="stored text",
            score=1.0,
            metadata={"source": "persisted.md"},
        )
    ]


def test_get_by_metadata_returns_matching_records(tmp_path) -> None:
    store = ChromaStore(_settings(tmp_path))
    store.upsert(
        [
            VectorRecord(
                id="a",
                text="alpha",
                vector=[1.0],
                metadata={"source": "same.md", "page": 1},
            ),
            VectorRecord(
                id="b",
                text="beta",
                vector=[1.0],
                metadata={"source": "same.md", "page": 2},
            ),
            VectorRecord(
                id="c",
                text="gamma",
                vector=[1.0],
                metadata={"source": "other.md", "page": 1},
            ),
        ]
    )

    records = store.get_by_metadata({"source": "same.md"})

    assert [record.id for record in records] == ["a", "b"]


def test_get_by_ids_preserves_request_order_and_skips_missing(tmp_path) -> None:
    store = ChromaStore(_settings(tmp_path))
    store.upsert(
        [
            VectorRecord(id="a", text="alpha", vector=[1.0], metadata={"rank": 1}),
            VectorRecord(id="b", text="beta", vector=[1.0], metadata={"rank": 2}),
        ]
    )

    records = store.get_by_ids(["b", "missing", "a"])

    assert [(record.id, record.text) for record in records] == [
        ("b", "beta"),
        ("a", "alpha"),
    ]


def test_query_rejects_dimension_mismatch(tmp_path) -> None:
    store = ChromaStore(_settings(tmp_path))
    store.upsert([VectorRecord(id="a", text="alpha", vector=[1.0, 0.0])])

    with pytest.raises(ChromaStoreError, match="dimensions must match"):
        store.query([1.0], top_k=1)
