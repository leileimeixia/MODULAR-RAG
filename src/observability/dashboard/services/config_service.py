"""Dashboard-facing configuration and overview data service."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.settings import Settings, load_settings
from libs.vector_store.chroma_store import ChromaStore


class ConfigService:
    """Load settings and format safe dashboard overview data."""

    def __init__(self, settings_path: str | Path = "config/settings.yaml") -> None:
        self.settings_path = Path(settings_path)

    def load_settings(self) -> Settings:
        """Load project settings from the configured settings file."""
        return load_settings(self.settings_path)

    def component_cards(self, settings: Settings | None = None) -> list[dict[str, Any]]:
        """Return display-ready component cards without exposing secrets."""
        settings = settings or self.load_settings()
        return [
            _card("LLM", settings.llm.provider, settings.llm.model, settings.llm),
            _card(
                "Embedding",
                settings.embedding.provider,
                settings.embedding.model,
                settings.embedding,
            ),
            _card(
                "Vision LLM",
                settings.vision_llm.provider,
                settings.vision_llm.model,
                settings.vision_llm,
                status="enabled" if settings.vision_llm.enabled else "disabled",
            ),
            _card(
                "Vector Store",
                settings.vector_store.provider,
                settings.vector_store.collection_name,
                settings.vector_store,
            ),
            _card(
                "Splitter",
                settings.splitter.provider,
                f"size={settings.splitter.chunk_size}",
                settings.splitter,
            ),
            _card(
                "Retrieval",
                "hybrid",
                f"dense={settings.retrieval.dense_top_k}, sparse={settings.retrieval.sparse_top_k}",
                settings.retrieval,
            ),
            _card(
                "Rerank",
                settings.rerank.provider,
                settings.rerank.model or "none",
                settings.rerank,
                status="enabled" if settings.rerank.enabled else "disabled",
            ),
            _card(
                "Observability",
                "jsonl",
                settings.observability.trace_file,
                settings.observability,
                status="enabled" if settings.observability.trace_enabled else "disabled",
            ),
        ]

    def data_stats(self, settings: Settings | None = None) -> dict[str, Any]:
        """Return vector collection stats, degrading gracefully when unavailable."""
        settings = settings or self.load_settings()
        try:
            stats = ChromaStore(settings.vector_store).get_collection_stats()
        except Exception as exc:  # noqa: BLE001 - dashboard should show config errors.
            return {
                "status": "unavailable",
                "error": str(exc),
                "collection_name": settings.vector_store.collection_name,
                "persist_directory": settings.vector_store.persist_directory,
                "record_count": 0,
                "source_count": 0,
            }
        return {"status": "available", **stats}

    def overview(self) -> dict[str, Any]:
        """Return all data required by the system overview page."""
        settings = self.load_settings()
        return {
            "settings_path": str(self.settings_path),
            "components": self.component_cards(settings),
            "data_stats": self.data_stats(settings),
        }


def _card(
    name: str,
    provider: str,
    model: str,
    settings_section: Any,
    status: str = "configured",
) -> dict[str, Any]:
    return {
        "name": name,
        "provider": provider,
        "model": model,
        "status": status,
        "details": _safe_details(settings_section),
    }


def _safe_details(settings_section: Any) -> dict[str, Any]:
    details = asdict(settings_section)
    return {
        key: value
        for key, value in details.items()
        if key not in {"api_key"} and not key.endswith("_key")
    }
