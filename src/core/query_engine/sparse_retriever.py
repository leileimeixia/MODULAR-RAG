"""Sparse BM25 retriever."""

from __future__ import annotations

from typing import Any

from core import RetrievalResult
from ingestion.storage import BM25Indexer
from libs.vector_store import BaseVectorStore, VectorRecord, VectorStoreFactory


class SparseRetrieverError(ValueError):
    """Raised when sparse retrieval cannot complete."""


class SparseRetriever:
    """Retrieve chunk ids from BM25 and hydrate them from the vector store."""

    def __init__(
        self,
        settings: Any | None = None,
        bm25_indexer: Any | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        self.settings = settings
        self.bm25_indexer = bm25_indexer or BM25Indexer().load()
        self.vector_store = vector_store or VectorStoreFactory.create(settings)

    def retrieve(
        self,
        keywords: list[str],
        top_k: int,
        trace: Any | None = None,
    ) -> list[RetrievalResult]:
        """Return sparse retrieval results for normalized query keywords."""
        if not isinstance(keywords, list):
            raise SparseRetrieverError("keywords must be a list of strings")
        normalized_keywords = [
            keyword.strip()
            for keyword in keywords
            if isinstance(keyword, str) and keyword.strip()
        ]
        if not normalized_keywords:
            raise SparseRetrieverError(
                "keywords must include at least one non-empty string"
            )
        if len(normalized_keywords) != len(keywords):
            raise SparseRetrieverError("keywords must contain only non-empty strings")
        if top_k <= 0:
            raise SparseRetrieverError("top_k must be greater than 0")

        bm25_results = self.bm25_indexer.query(
            " ".join(normalized_keywords),
            top_k=top_k,
        )
        chunk_ids = [
            str(result["chunk_id"])
            for result in bm25_results
            if result.get("chunk_id")
        ]
        if not chunk_ids:
            self._record_trace(trace, top_k, len(normalized_keywords), 0, 0, 0)
            return []

        records = self.vector_store.get_by_ids(chunk_ids, trace=trace)
        records_by_id = {record.id: record for record in records}
        retrieval_results: list[RetrievalResult] = []
        for result in bm25_results:
            chunk_id = str(result.get("chunk_id", ""))
            record = records_by_id.get(chunk_id)
            if record is None:
                continue
            retrieval_results.append(_to_retrieval_result(record, float(result["score"])))

        self._record_trace(
            trace,
            top_k,
            len(normalized_keywords),
            len(bm25_results),
            len(retrieval_results),
            len(chunk_ids) - len(retrieval_results),
        )
        return retrieval_results

    def _record_trace(
        self,
        trace: Any | None,
        top_k: int,
        keyword_count: int,
        candidate_count: int,
        result_count: int,
        missing_count: int,
    ) -> None:
        if trace is not None:
            trace.record_stage(
                "sparse_retrieval",
                method=self.bm25_indexer.__class__.__name__,
                details={
                    "top_k": top_k,
                    "keyword_count": keyword_count,
                    "candidate_count": candidate_count,
                    "result_count": result_count,
                    "missing_count": missing_count,
                },
            )


def _to_retrieval_result(record: VectorRecord, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=record.id,
        score=score,
        text=record.text,
        metadata=dict(record.metadata),
    )
