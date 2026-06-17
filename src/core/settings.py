"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class SettingsError(ValueError):
    """Raised when project settings are missing or invalid."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    dimensions: int
    api_key: str = ""


@dataclass(frozen=True)
class VisionLLMSettings:
    enabled: bool
    provider: str
    model: str
    api_key: str = ""
    max_image_size: int = 2048


@dataclass(frozen=True)
class VectorStoreSettings:
    provider: str
    persist_directory: str
    collection_name: str


@dataclass(frozen=True)
class RetrievalSettings:
    dense_top_k: int
    sparse_top_k: int
    fusion_top_k: int
    rrf_k: int


@dataclass(frozen=True)
class SplitterSettings:
    provider: str = "recursive"
    chunk_size: int = 1000
    chunk_overlap: int = 200


@dataclass(frozen=True)
class RerankSettings:
    enabled: bool
    provider: str
    model: str = ""
    top_k: int = 5


@dataclass(frozen=True)
class EvaluationSettings:
    enabled: bool
    provider: str


@dataclass(frozen=True)
class ObservabilitySettings:
    log_level: str
    trace_enabled: bool
    trace_file: str


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings
    embedding: EmbeddingSettings
    vision_llm: VisionLLMSettings
    vector_store: VectorStoreSettings
    retrieval: RetrievalSettings
    rerank: RerankSettings
    evaluation: EvaluationSettings
    observability: ObservabilitySettings
    splitter: SplitterSettings = field(default_factory=SplitterSettings)


_ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    """Load settings from YAML and validate required fields."""
    settings_path = Path(path)
    if not settings_path.exists():
        raise SettingsError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    if not isinstance(raw, dict):
        raise SettingsError("settings.yaml must contain a mapping at the root")

    expanded = _expand_env_values(raw)
    settings = _parse_settings(expanded)
    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    """Validate required fields and raise readable field-path errors."""
    required: list[tuple[str, Any]] = [
        ("llm.provider", settings.llm.provider),
        ("llm.model", settings.llm.model),
        ("embedding.provider", settings.embedding.provider),
        ("embedding.model", settings.embedding.model),
        ("embedding.dimensions", settings.embedding.dimensions),
        ("vector_store.provider", settings.vector_store.provider),
        ("vector_store.persist_directory", settings.vector_store.persist_directory),
        ("vector_store.collection_name", settings.vector_store.collection_name),
        ("retrieval.dense_top_k", settings.retrieval.dense_top_k),
        ("retrieval.sparse_top_k", settings.retrieval.sparse_top_k),
        ("retrieval.fusion_top_k", settings.retrieval.fusion_top_k),
        ("retrieval.rrf_k", settings.retrieval.rrf_k),
        ("splitter.provider", settings.splitter.provider),
        ("splitter.chunk_size", settings.splitter.chunk_size),
        ("splitter.chunk_overlap", settings.splitter.chunk_overlap),
        ("rerank.enabled", settings.rerank.enabled),
        ("rerank.provider", settings.rerank.provider),
        ("evaluation.enabled", settings.evaluation.enabled),
        ("evaluation.provider", settings.evaluation.provider),
        ("observability.log_level", settings.observability.log_level),
        ("observability.trace_enabled", settings.observability.trace_enabled),
        ("observability.trace_file", settings.observability.trace_file),
    ]
    for field_path, value in required:
        if value is None or value == "":
            raise SettingsError(f"Missing required field: {field_path}")

    if settings.embedding.dimensions <= 0:
        raise SettingsError("embedding.dimensions must be greater than 0")
    if settings.splitter.chunk_size <= 0:
        raise SettingsError("splitter.chunk_size must be greater than 0")
    if settings.splitter.chunk_overlap < 0:
        raise SettingsError("splitter.chunk_overlap must be greater than or equal to 0")


def _parse_settings(raw: dict[str, Any]) -> Settings:
    return Settings(
        llm=LLMSettings(**_section(raw, "llm")),
        embedding=EmbeddingSettings(**_section(raw, "embedding")),
        vision_llm=VisionLLMSettings(**_section(raw, "vision_llm")),
        vector_store=VectorStoreSettings(**_section(raw, "vector_store")),
        retrieval=RetrievalSettings(**_section(raw, "retrieval")),
        rerank=RerankSettings(**_section(raw, "rerank")),
        evaluation=EvaluationSettings(**_section(raw, "evaluation")),
        observability=ObservabilitySettings(**_section(raw, "observability")),
        splitter=SplitterSettings(**raw.get("splitter", {})),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise SettingsError(f"Missing required section: {name}")
    return value


def _expand_env_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env_values(item) for item in value]
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value)
        if match:
            return os.getenv(match.group(1), "")
    return value
