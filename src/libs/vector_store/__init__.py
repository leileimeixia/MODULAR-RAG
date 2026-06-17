"""Vector store abstractions."""

from .base_vector_store import BaseVectorStore, VectorQueryResult, VectorRecord
from .vector_store_factory import VectorStoreFactory, VectorStoreFactoryError

__all__ = [
    "BaseVectorStore",
    "VectorQueryResult",
    "VectorRecord",
    "VectorStoreFactory",
    "VectorStoreFactoryError",
]
