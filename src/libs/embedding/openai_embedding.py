"""OpenAI-compatible embedding clients."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.settings import EmbeddingSettings

from .base_embedding import BaseEmbedding, Vector


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider call fails."""


@dataclass(frozen=True)
class OpenAIEmbeddingConfig:
    """HTTP settings for an OpenAI-compatible embedding endpoint."""

    provider: str
    endpoint: str
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    timeout_seconds: float = 60.0


class OpenAICompatibleEmbedding(BaseEmbedding):
    """Minimal OpenAI-compatible embeddings client."""

    def __init__(
        self,
        settings: EmbeddingSettings,
        config: OpenAIEmbeddingConfig,
    ) -> None:
        self.settings = settings
        self.config = config

    def embed(self, texts: list[str], trace: Any | None = None) -> list[Vector]:
        """Embed a batch of texts and return dense vectors."""
        _validate_texts(texts, self.config.provider)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "input": texts,
        }
        if self.settings.dimensions:
            payload["dimensions"] = self.settings.dimensions

        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers[self.config.auth_header] = (
                f"{self.config.auth_prefix}{self.settings.api_key}"
            )

        request = Request(
            self.config.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise EmbeddingProviderError(
                f"{self.config.provider} embedding request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise EmbeddingProviderError(
                f"{self.config.provider} embedding request failed: {reason}"
            ) from exc
        except TimeoutError as exc:
            raise EmbeddingProviderError(
                f"{self.config.provider} embedding request timed out"
            ) from exc

        return _parse_embedding_response(raw_body, self.config.provider)


class OpenAIEmbedding(OpenAICompatibleEmbedding):
    """OpenAI embedding provider."""

    def __init__(self, settings: EmbeddingSettings) -> None:
        super().__init__(
            settings,
            OpenAIEmbeddingConfig(
                provider="openai",
                endpoint="https://api.openai.com/v1/embeddings",
            ),
        )


def _validate_texts(texts: list[str], provider: str) -> None:
    if not isinstance(texts, list) or not texts:
        raise EmbeddingProviderError(
            f"{provider} embedding requires a non-empty texts list"
        )
    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise EmbeddingProviderError(
                f"{provider} embedding input at index {index} must be a string"
            )
        if not text:
            raise EmbeddingProviderError(
                f"{provider} embedding input at index {index} must not be empty"
            )


def _parse_embedding_response(raw_body: str, provider: str) -> list[Vector]:
    try:
        payload: Any = json.loads(raw_body)
        items = payload["data"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise EmbeddingProviderError(
            f"{provider} embedding response has unexpected shape"
        ) from exc

    if not isinstance(items, list):
        raise EmbeddingProviderError(
            f"{provider} embedding response data must be a list"
        )

    vectors: list[Vector] = []
    for index, item in enumerate(items):
        try:
            embedding = item["embedding"]
        except (KeyError, TypeError) as exc:
            raise EmbeddingProviderError(
                f"{provider} embedding item at index {index} has unexpected shape"
            ) from exc
        if not isinstance(embedding, list) or not all(
            isinstance(value, int | float) for value in embedding
        ):
            raise EmbeddingProviderError(
                f"{provider} embedding item at index {index} must be numeric vector"
            )
        vectors.append([float(value) for value in embedding])

    return vectors
