"""Tests for vision LLM abstractions and factory routing."""

from __future__ import annotations

from pathlib import Path

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
from libs.llm import BaseVisionLLM, LLMFactory, LLMFactoryError, VisionLLMResponse


class FakeVisionLLM(BaseVisionLLM):
    def __init__(self, settings: VisionLLMSettings) -> None:
        self.settings = settings
        self.calls: list[tuple[str, str | Path | bytes]] = []

    def chat_with_image(self, text: str, image_path: str | Path | bytes, trace=None) -> str:
        self.calls.append((text, image_path))
        return f"{self.settings.model}: {text}"


@pytest.fixture(autouse=True)
def clean_vision_registry():
    LLMFactory.unregister_vision("fake")
    yield
    LLMFactory.unregister_vision("fake")


def _settings(provider: str = "fake", enabled: bool = True) -> Settings:
    return Settings(
        llm=LLMSettings(provider="openai", model="gpt-5.5"),
        embedding=EmbeddingSettings(
            provider="openai",
            model="text-embedding-ada-002",
            dimensions=1536,
        ),
        vision_llm=VisionLLMSettings(
            enabled=enabled,
            provider=provider,
            model="vision-model",
            api_key="key",
            max_image_size=2048,
        ),
        vector_store=VectorStoreSettings(
            provider="chroma",
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


def test_factory_creates_registered_vision_provider_from_full_settings() -> None:
    LLMFactory.register_vision("fake", FakeVisionLLM)

    vision_llm = LLMFactory.create_vision_llm(_settings())

    assert isinstance(vision_llm, FakeVisionLLM)
    assert vision_llm.settings.model == "vision-model"
    assert vision_llm.chat_with_image("describe", "image.png") == (
        "vision-model: describe"
    )


def test_factory_creates_registered_vision_provider_from_vision_settings() -> None:
    LLMFactory.register_vision("fake", FakeVisionLLM)

    vision_llm = LLMFactory.create_vision_llm(
        VisionLLMSettings(
            enabled=True,
            provider="fake",
            model="vision",
        )
    )

    assert isinstance(vision_llm, FakeVisionLLM)


def test_factory_normalizes_vision_provider_names() -> None:
    LLMFactory.register_vision("fake-provider", FakeVisionLLM)

    vision_llm = LLMFactory.create_vision_llm(
        VisionLLMSettings(
            enabled=True,
            provider=" FAKE_PROVIDER ",
            model="vision",
        )
    )

    assert isinstance(vision_llm, FakeVisionLLM)
    LLMFactory.unregister_vision("fake-provider")


def test_factory_rejects_disabled_vision_llm() -> None:
    with pytest.raises(LLMFactoryError, match="disabled"):
        LLMFactory.create_vision_llm(_settings(enabled=False))


def test_factory_rejects_unknown_vision_provider() -> None:
    with pytest.raises(
        LLMFactoryError,
        match="Unsupported vision LLM provider 'missing'",
    ):
        LLMFactory.create_vision_llm(_settings(provider="missing"))


def test_base_vision_llm_requires_chat_with_image_implementation() -> None:
    with pytest.raises(TypeError):
        BaseVisionLLM()


def test_vision_response_shape() -> None:
    response = VisionLLMResponse(text="caption", raw={"id": "raw"})

    assert response.text == "caption"
    assert response.raw == {"id": "raw"}
