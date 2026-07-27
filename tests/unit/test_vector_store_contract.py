"""Contract tests for vector store abstractions and factory routing."""

from __future__ import annotations

import pytest

from core.settings import (
    EmbeddingSettings,
    EvaluationSettings,
    LLMSettings,
    ObservabilitySettings,
    RerankSettings,
    RetrievalSettings,
    Settings,
    VectorStoreSettings,
    VisionLLMSettings,
)
from libs.vector_store import (
    BaseVectorStore,
    VectorQueryResult,
    VectorRecord,
    VectorStoreFactory,
    VectorStoreFactoryError,
)


class FakeVectorStore(BaseVectorStore):
    def __init__(self, settings: VectorStoreSettings) -> None:
        self.settings = settings
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord], trace=None) -> None:
        for record in records:
            self.records[record.id] = record

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict | None = None,
        trace=None,
    ) -> list[VectorQueryResult]:
        filters = filters or {}
        matched = [
            record
            for record in self.records.values()
            if all(record.metadata.get(key) == value for key, value in filters.items())
        ]
        return [
            VectorQueryResult(
                id=record.id,
                text=record.text,
                score=_dot(vector, record.vector),
                metadata=record.metadata,
            )
            for record in sorted(matched, key=lambda item: item.id)[:top_k]
        ]

    def get_by_ids(self, ids: list[str], trace=None) -> list[VectorRecord]:
        return [
            self.records[record_id]
            for record_id in ids
            if record_id in self.records
        ]

    def delete_by_metadata(self, filters: dict) -> int:
        if not isinstance(filters, dict) or not filters:
            raise ValueError("delete_by_metadata filters must be a non-empty dictionary")
        matched_ids = [
            record.id
            for record in self.records.values()
            if all(record.metadata.get(key) == value for key, value in filters.items())
        ]
        for record_id in matched_ids:
            self.records.pop(record_id, None)
        return len(matched_ids)


@pytest.fixture(autouse=True)
def clean_registry():
    VectorStoreFactory.unregister("fake")
    yield
    VectorStoreFactory.unregister("fake")


def _settings(provider: str = "fake") -> Settings:
    return Settings(
        llm=LLMSettings(provider="openai", model="gpt-5.5"),
        embedding=EmbeddingSettings(
            provider="openai",
            model="text-embedding-ada-002",
            dimensions=1536,
        ),
        vision_llm=VisionLLMSettings(
            enabled=False,
            provider="openai",
            model="gpt-4o",
        ),
        vector_store=VectorStoreSettings(
            provider=provider,
            persist_directory="./data/db/chroma",
            collection_name="knowledge_hub",
        ),
        retrieval=RetrievalSettings(
            dense_top_k=20,
            sparse_top_k=20,
            fusion_top_k=10,
            rrf_k=60,
        ),
        rerank=RerankSettings(enabled=False, provider="none"),
        evaluation=EvaluationSettings(enabled=False, provider="custom"),
        observability=ObservabilitySettings(
            log_level="INFO",
            trace_enabled=True,
            trace_file="./logs/traces.jsonl",
        ),
    )


def test_factory_creates_registered_provider_from_full_settings() -> None:
    VectorStoreFactory.register("fake", FakeVectorStore)

    store = VectorStoreFactory.create(_settings())

    assert isinstance(store, FakeVectorStore)
    assert store.settings.collection_name == "knowledge_hub"


def test_factory_creates_registered_provider_from_vector_store_settings() -> None:
    VectorStoreFactory.register("fake", FakeVectorStore)

    store = VectorStoreFactory.create(
        VectorStoreSettings(
            provider="fake",
            persist_directory="./tmp",
            collection_name="test",
        )
    )

    assert isinstance(store, FakeVectorStore)
    assert store.settings.persist_directory == "./tmp"


def test_vector_store_contract_upsert_and_query_shape() -> None:
    store = FakeVectorStore(
        VectorStoreSettings(
            provider="fake",
            persist_directory="./tmp",
            collection_name="test",
        )
    )
    store.upsert(
        [
            VectorRecord(
                id="a",
                text="alpha",
                vector=[1.0, 0.0],
                metadata={"collection": "docs"},
            ),
            VectorRecord(
                id="b",
                text="beta",
                vector=[0.0, 1.0],
                metadata={"collection": "other"},
            ),
        ]
    )

    results = store.query([1.0, 0.0], top_k=5, filters={"collection": "docs"})

    assert results == [
        VectorQueryResult(
            id="a",
            text="alpha",
            score=1.0,
            metadata={"collection": "docs"},
        )
    ]


def test_vector_store_contract_get_by_ids_preserves_order_and_skips_missing() -> None:
    store = FakeVectorStore(
        VectorStoreSettings(
            provider="fake",
            persist_directory="./tmp",
            collection_name="test",
        )
    )
    store.upsert(
        [
            VectorRecord(id="a", text="alpha", vector=[1.0], metadata={}),
            VectorRecord(id="b", text="beta", vector=[1.0], metadata={}),
        ]
    )

    records = store.get_by_ids(["b", "missing", "a"])

    assert [record.id for record in records] == ["b", "a"]


def test_vector_store_contract_delete_by_metadata_requires_non_empty_filters() -> None:
    store = FakeVectorStore(
        VectorStoreSettings(
            provider="fake",
            persist_directory="./tmp",
            collection_name="test",
        )
    )

    with pytest.raises(ValueError, match="non-empty dictionary"):
        store.delete_by_metadata({})


def test_vector_store_contract_delete_by_metadata_matches_all_filters() -> None:
    store = FakeVectorStore(
        VectorStoreSettings(
            provider="fake",
            persist_directory="./tmp",
            collection_name="test",
        )
    )
    store.upsert(
        [
            VectorRecord(
                id="a",
                text="alpha",
                vector=[1.0],
                metadata={"source_path": "guide.pdf", "collection": "docs"},
            ),
            VectorRecord(
                id="b",
                text="beta",
                vector=[1.0],
                metadata={"source_path": "guide.pdf", "collection": "other"},
            ),
            VectorRecord(
                id="c",
                text="gamma",
                vector=[1.0],
                metadata={"source_path": "manual.pdf", "collection": "docs"},
            ),
        ]
    )

    deleted = store.delete_by_metadata({"source_path": "guide.pdf", "collection": "docs"})

    assert deleted == 1
    assert sorted(store.records) == ["b", "c"]


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(
        VectorStoreFactoryError,
        match="Unsupported vector store provider 'missing'",
    ):
        VectorStoreFactory.create(_settings(provider="missing"))


def test_factory_rejects_empty_provider() -> None:
    with pytest.raises(
        VectorStoreFactoryError,
        match="provider must be a non-empty string",
    ):
        VectorStoreFactory.create(_settings(provider=" "))


def test_base_vector_store_requires_methods() -> None:
    with pytest.raises(TypeError):
        BaseVectorStore()


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
