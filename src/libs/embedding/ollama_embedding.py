"""Ollama local embedding client."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.settings import EmbeddingSettings

from .base_embedding import BaseEmbedding, Vector
from .openai_embedding import EmbeddingProviderError


class OllamaEmbedding(BaseEmbedding):
    """Embedding provider for Ollama's native `/api/embed` endpoint."""

    def __init__(self, settings: EmbeddingSettings) -> None:
        self.settings = settings
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.endpoint = f"{self.base_url}/api/embed"

    def embed(self, texts: list[str], trace: Any | None = None) -> list[Vector]:
        """Embed a batch of texts through Ollama."""
        _validate_texts(texts)
        payload = {
            "model": self.settings.model,
            "input": texts,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60.0) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise EmbeddingProviderError(
                f"ollama embedding request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise EmbeddingProviderError(
                f"ollama embedding request failed: {reason}"
            ) from exc
        except TimeoutError as exc:
            raise EmbeddingProviderError("ollama embedding request timed out") from exc

        return _parse_ollama_response(raw_body)


def _validate_texts(texts: list[str]) -> None:
    if not isinstance(texts, list) or not texts:
        raise EmbeddingProviderError(
            "ollama embedding requires a non-empty texts list"
        )
    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise EmbeddingProviderError(
                f"ollama embedding input at index {index} must be a string"
            )
        if not text:
            raise EmbeddingProviderError(
                f"ollama embedding input at index {index} must not be empty"
            )


def _parse_ollama_response(raw_body: str) -> list[Vector]:
    try:
        payload: Any = json.loads(raw_body)
        embeddings = payload["embeddings"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise EmbeddingProviderError(
            "ollama embedding response has unexpected shape"
        ) from exc

    if not isinstance(embeddings, list):
        raise EmbeddingProviderError("ollama embedding response embeddings must be a list")

    vectors: list[Vector] = []
    for index, embedding in enumerate(embeddings):
        if not isinstance(embedding, list) or not all(
            isinstance(value, int | float) for value in embedding
        ):
            raise EmbeddingProviderError(
                f"ollama embedding item at index {index} must be numeric vector"
            )
        vectors.append([float(value) for value in embedding])
    return vectors
