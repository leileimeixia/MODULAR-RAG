"""Smoke tests for OpenAI-compatible embedding providers."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from core.settings import EmbeddingSettings
from libs.embedding import (
    AzureEmbedding,
    EmbeddingFactory,
    EmbeddingProviderError,
    OpenAIEmbedding,
)
from libs.embedding import openai_embedding


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_factory_routes_openai_and_azure_embedding_providers() -> None:
    assert isinstance(
        EmbeddingFactory.create(
            EmbeddingSettings(
                provider="openai",
                model="text-embedding-3-small",
                dimensions=1536,
            )
        ),
        OpenAIEmbedding,
    )
    assert isinstance(
        EmbeddingFactory.create(
            EmbeddingSettings(
                provider="azure",
                model="text-embedding-ada-002",
                dimensions=1536,
            )
        ),
        AzureEmbedding,
    )


def test_openai_embedding_posts_expected_shape(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {"data": [{"embedding": [1, 2.5, 3]}, {"embedding": [4.0, 5, 6]}]}
        )

    monkeypatch.setattr(openai_embedding, "urlopen", fake_urlopen)
    embedding = OpenAIEmbedding(
        EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="secret",
        )
    )

    vectors = embedding.embed(["hello", "world"])

    assert vectors == [[1.0, 2.5, 3.0], [4.0, 5.0, 6.0]]
    assert captured["url"] == "https://api.openai.com/v1/embeddings"
    assert captured["payload"] == {
        "model": "text-embedding-3-small",
        "input": ["hello", "world"],
        "dimensions": 1536,
    }
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_azure_embedding_uses_deployment_url_and_api_key_header(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://unit-test.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-01-01")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeHTTPResponse({"data": [{"embedding": [0.1, 0.2]}]})

    monkeypatch.setattr(openai_embedding, "urlopen", fake_urlopen)
    embedding = AzureEmbedding(
        EmbeddingSettings(
            provider="azure",
            model="embedding deployment",
            dimensions=1536,
            api_key="key",
        )
    )

    assert embedding.embed(["hello"]) == [[0.1, 0.2]]
    assert captured["url"] == (
        "https://unit-test.openai.azure.com/openai/deployments/"
        "embedding%20deployment/embeddings?api-version=2024-01-01"
    )
    assert captured["headers"]["Api-key"] == "key"


def test_embedding_rejects_empty_or_invalid_inputs() -> None:
    embedding = OpenAIEmbedding(
        EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536)
    )

    with pytest.raises(EmbeddingProviderError, match="non-empty texts list"):
        embedding.embed([])

    with pytest.raises(EmbeddingProviderError, match="must be a string"):
        embedding.embed(["ok", 123])

    with pytest.raises(EmbeddingProviderError, match="must not be empty"):
        embedding.embed([""])


def test_embedding_wraps_http_errors_without_leaking_api_key(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized secret-key",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(openai_embedding, "urlopen", fake_urlopen)
    embedding = OpenAIEmbedding(
        EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="secret",
        )
    )

    with pytest.raises(EmbeddingProviderError) as exc_info:
        embedding.embed(["hello"])

    assert "HTTP 401" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_embedding_wraps_connection_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(openai_embedding, "urlopen", fake_urlopen)
    embedding = OpenAIEmbedding(
        EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536)
    )

    with pytest.raises(EmbeddingProviderError, match="openai embedding request failed"):
        embedding.embed(["hello"])


def test_embedding_rejects_unexpected_response_shape(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"data": [{"embedding": ["bad"]}]})

    monkeypatch.setattr(openai_embedding, "urlopen", fake_urlopen)
    embedding = OpenAIEmbedding(
        EmbeddingSettings(provider="openai", model="text-embedding-3-small", dimensions=1536)
    )

    with pytest.raises(EmbeddingProviderError, match="numeric vector"):
        embedding.embed(["hello"])
