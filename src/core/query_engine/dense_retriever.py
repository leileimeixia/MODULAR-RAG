"""Dense vector retriever."""

from __future__ import annotations

from typing import Any

from core import RetrievalResult
from libs.embedding import BaseEmbedding, EmbeddingFactory
from libs.vector_store import BaseVectorStore, VectorStoreFactory


class DenseRetrieverError(ValueError):
    """Raised when dense retrieval cannot complete."""


class DenseRetriever:
    """Embed a query and retrieve nearest chunks from a vector store."""

    def __init__(
        self,
        settings: Any | None = None,
        embedding_client: BaseEmbedding | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_client = embedding_client or EmbeddingFactory.create(settings)
        self.vector_store = vector_store or VectorStoreFactory.create(settings)

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
        trace: Any | None = None,
    ) -> list[RetrievalResult]:
        """Return dense retrieval results for a raw query string."""
        if not isinstance(query, str) or not query.strip():
            raise DenseRetrieverError("query must be a non-empty string")
        if top_k <= 0:
            raise DenseRetrieverError("top_k must be greater than 0")
        if filters is not None and not isinstance(filters, dict):
            raise DenseRetrieverError("filters must be a dictionary")

        vectors = self.embedding_client.embed([query], trace=trace)
        if len(vectors) != 1:
            raise DenseRetrieverError(
                f"embedding returned {len(vectors)} vectors for one query"
            )
        vector = vectors[0]
        if not vector:
            raise DenseRetrieverError("embedding returned an empty query vector")

        results = self.vector_store.query(
            vector,
            top_k=top_k,
            filters=filters or {},
            trace=trace,
        )
        retrieval_results = [
            RetrievalResult(
                chunk_id=result.id,
                score=float(result.score),
                text=result.text,
                metadata=dict(result.metadata),
            )
            for result in results
        ]
        if trace is not None:
            trace.record_stage(
                "dense_retrieval",
                method=self.vector_store.__class__.__name__,
                details={
                    "top_k": top_k,
                    "result_count": len(retrieval_results),
                    "filters": filters or {},
                },
            )
        return retrieval_results
