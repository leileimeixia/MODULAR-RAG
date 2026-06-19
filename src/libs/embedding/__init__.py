"""Embedding abstractions."""

from .azure_embedding import AzureEmbedding
from .base_embedding import BaseEmbedding, EmbeddingResponse, Vector
from .embedding_factory import EmbeddingFactory, EmbeddingFactoryError
from .ollama_embedding import OllamaEmbedding
from .openai_embedding import (
    EmbeddingProviderError,
    OpenAICompatibleEmbedding,
    OpenAIEmbedding,
)

__all__ = [
    "AzureEmbedding",
    "BaseEmbedding",
    "EmbeddingFactory",
    "EmbeddingFactoryError",
    "EmbeddingProviderError",
    "EmbeddingResponse",
    "OllamaEmbedding",
    "OpenAICompatibleEmbedding",
    "OpenAIEmbedding",
    "Vector",
]
