"""Embedding abstractions."""

from .base_embedding import BaseEmbedding, EmbeddingResponse, Vector
from .embedding_factory import EmbeddingFactory, EmbeddingFactoryError

__all__ = [
    "BaseEmbedding",
    "EmbeddingFactory",
    "EmbeddingFactoryError",
    "EmbeddingResponse",
    "Vector",
]
