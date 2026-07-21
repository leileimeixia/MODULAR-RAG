"""Tests for dashboard configuration service."""

from __future__ import annotations

import yaml

from libs.vector_store import ChromaStore, VectorRecord
from observability.dashboard.services.config_service import ConfigService


def test_config_service_formats_safe_component_cards(tmp_path) -> None:
    settings_path = _write_settings(tmp_path)
    service = ConfigService(settings_path)

    cards = service.component_cards()

    assert [card["name"] for card in cards] == [
        "LLM",
        "Embedding",
        "Vision LLM",
        "Vector Store",
        "Splitter",
        "Retrieval",
        "Rerank",
        "Observability",
    ]
    assert all("api_key" not in card["details"] for card in cards)


def test_config_service_returns_collection_stats(tmp_path) -> None:
    settings_path = _write_settings(tmp_path)
    settings = ConfigService(settings_path).load_settings()
    ChromaStore(settings.vector_store).upsert(
        [
            VectorRecord(
                id="a",
                text="alpha",
                vector=[1.0],
                metadata={"source_path": "docs/a.md"},
            ),
            VectorRecord(
                id="b",
                text="beta",
                vector=[1.0],
                metadata={"source_path": "docs/a.md"},
            ),
            VectorRecord(
                id="c",
                text="gamma",
                vector=[1.0],
                metadata={"source_path": "docs/b.md"},
            ),
        ]
    )

    stats = ConfigService(settings_path).data_stats()

    assert stats["status"] == "available"
    assert stats["collection_name"] == "dashboard_test"
    assert stats["record_count"] == 3
    assert stats["source_count"] == 2


def test_chroma_store_collection_stats(tmp_path) -> None:
    settings_path = _write_settings(tmp_path)
    settings = ConfigService(settings_path).load_settings()
    store = ChromaStore(settings.vector_store)
    store.upsert(
        [
            VectorRecord(
                id="chunk-1",
                text="content",
                vector=[1.0, 0.0],
                metadata={"source": "sample.md"},
            )
        ]
    )

    stats = store.get_collection_stats()

    assert stats["provider"] == "chroma"
    assert stats["record_count"] == 1
    assert stats["source_count"] == 1


def _write_settings(tmp_path):
    persist_directory = tmp_path / "vectors"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-test",
                    "api_key": "secret",
                },
                "embedding": {
                    "provider": "openai",
                    "model": "text-embedding-test",
                    "dimensions": 1,
                    "api_key": "secret",
                },
                "vision_llm": {
                    "enabled": True,
                    "provider": "openai",
                    "model": "gpt-vision-test",
                    "api_key": "secret",
                },
                "vector_store": {
                    "provider": "chroma",
                    "persist_directory": str(persist_directory),
                    "collection_name": "dashboard_test",
                },
                "retrieval": {
                    "dense_top_k": 5,
                    "sparse_top_k": 5,
                    "fusion_top_k": 5,
                    "rrf_k": 60,
                },
                "splitter": {
                    "provider": "recursive",
                    "chunk_size": 1000,
                    "chunk_overlap": 200,
                },
                "rerank": {
                    "enabled": False,
                    "provider": "none",
                    "model": "",
                    "top_k": 5,
                },
                "evaluation": {
                    "enabled": False,
                    "provider": "custom",
                },
                "observability": {
                    "log_level": "INFO",
                    "trace_enabled": True,
                    "trace_file": "logs/traces.jsonl",
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return settings_path
