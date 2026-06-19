"""Tests for the Ollama embedding provider."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from core.settings import EmbeddingSettings
from libs.embedding import EmbeddingFactory, EmbeddingProviderError, OllamaEmbedding
from libs.embedding import ollama_embedding


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_factory_creates_ollama_embedding_provider() -> None:
    embedding = EmbeddingFactory.create(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    assert isinstance(embedding, OllamaEmbedding)
    assert embedding.endpoint == "http://localhost:11434/api/embed"


def test_ollama_embedding_posts_batch_request_shape(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://unit-test:11434/")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"embeddings": [[1, 2.5], [3.0, 4]]})

    monkeypatch.setattr(ollama_embedding, "urlopen", fake_urlopen)
    embedding = OllamaEmbedding(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    vectors = embedding.embed(["hello", "world"])

    assert vectors == [[1.0, 2.5], [3.0, 4.0]]
    assert captured["url"] == "http://unit-test:11434/api/embed"
    assert captured["payload"] == {
        "model": "nomic-embed-text",
        "input": ["hello", "world"],
    }
    assert captured["headers"]["Content-type"] == "application/json"


def test_ollama_embedding_rejects_empty_or_invalid_inputs() -> None:
    embedding = OllamaEmbedding(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    with pytest.raises(EmbeddingProviderError, match="non-empty texts list"):
        embedding.embed([])

    with pytest.raises(EmbeddingProviderError, match="must be a string"):
        embedding.embed(["ok", 123])

    with pytest.raises(EmbeddingProviderError, match="must not be empty"):
        embedding.embed([""])


def test_ollama_embedding_wraps_http_errors_without_leaking_details(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="server error with private path",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(ollama_embedding, "urlopen", fake_urlopen)
    embedding = OllamaEmbedding(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    with pytest.raises(EmbeddingProviderError, match="HTTP 500") as exc_info:
        embedding.embed(["hello"])

    assert "private path" not in str(exc_info.value)


def test_ollama_embedding_wraps_connection_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(ollama_embedding, "urlopen", fake_urlopen)
    embedding = OllamaEmbedding(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    with pytest.raises(EmbeddingProviderError, match="ollama embedding request failed"):
        embedding.embed(["hello"])


def test_ollama_embedding_rejects_unexpected_response_shape(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"embedding": [1, 2, 3]})

    monkeypatch.setattr(ollama_embedding, "urlopen", fake_urlopen)
    embedding = OllamaEmbedding(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    with pytest.raises(EmbeddingProviderError, match="unexpected shape"):
        embedding.embed(["hello"])


def test_ollama_embedding_rejects_non_numeric_vectors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"embeddings": [[1, "bad"]]})

    monkeypatch.setattr(ollama_embedding, "urlopen", fake_urlopen)
    embedding = OllamaEmbedding(
        EmbeddingSettings(provider="ollama", model="nomic-embed-text", dimensions=768)
    )

    with pytest.raises(EmbeddingProviderError, match="numeric vector"):
        embedding.embed(["hello"])
