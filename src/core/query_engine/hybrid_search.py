"""Hybrid retrieval orchestration."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from core import RetrievalResult

from .dense_retriever import DenseRetriever
from .fusion import RRFusion
from .query_processor import QueryProcessor
from .sparse_retriever import SparseRetriever


class HybridSearchError(ValueError):
    """Raised when hybrid search cannot return usable results."""


class HybridSearch:
    """Orchestrate query processing, dense retrieval, sparse retrieval, and fusion."""

    def __init__(
        self,
        settings: Any | None = None,
        query_processor: QueryProcessor | None = None,
        dense_retriever: DenseRetriever | None = None,
        sparse_retriever: SparseRetriever | None = None,
        fusion: RRFusion | None = None,
    ) -> None:
        self.settings = settings
        self.query_processor = query_processor or QueryProcessor()
        self.dense_retriever = dense_retriever or DenseRetriever(settings=settings)
        self.sparse_retriever = sparse_retriever or SparseRetriever(settings=settings)
        self.fusion = fusion or RRFusion(settings=settings)

    def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
        trace: Any | None = None,
    ) -> list[RetrievalResult]:
        """Return hybrid retrieval results for a raw query."""
        if top_k <= 0:
            raise HybridSearchError("top_k must be greater than 0")
        if filters is not None and not isinstance(filters, dict):
            raise HybridSearchError("filters must be a dictionary")

        start = time.perf_counter()
        processed = self.query_processor.process(query, filters=filters, trace=None)
        _record_timed_stage(
            trace,
            "query_processing",
            method=self.query_processor.__class__.__name__,
            started_at=start,
            details={
                "keyword_count": len(processed.keywords),
                "filter_keys": sorted(processed.filters),
            },
        )
        dense_top_k = _retrieval_top_k(self.settings, "dense_top_k", top_k)
        sparse_top_k = _retrieval_top_k(self.settings, "sparse_top_k", top_k)
        fusion_top_k = max(_retrieval_top_k(self.settings, "fusion_top_k", top_k), top_k)

        dense_results, dense_error = self._run_route(
            "dense_retrieval",
            self.dense_retriever.__class__.__name__,
            lambda: self.dense_retriever.retrieve(
                processed.query,
                top_k=dense_top_k,
                filters=processed.filters,
                trace=None,
            ),
            trace,
        )
        sparse_results, sparse_error = self._run_route(
            "sparse_retrieval",
            self.sparse_retriever.__class__.__name__,
            lambda: self.sparse_retriever.retrieve(
                processed.keywords,
                top_k=sparse_top_k,
                trace=None,
            ),
            trace,
        )
        if dense_error is not None and sparse_error is not None:
            raise HybridSearchError(
                "both dense and sparse retrieval failed"
            ) from dense_error

        start = time.perf_counter()
        fused = self.fusion.fuse(
            dense_results,
            sparse_results,
            top_k=fusion_top_k,
            trace=None,
        )
        _record_timed_stage(
            trace,
            "fusion",
            method=self.fusion.__class__.__name__,
            started_at=start,
            details={
                "top_k": fusion_top_k,
                "dense_count": len(dense_results),
                "sparse_count": len(sparse_results),
                "result_count": len(fused),
            },
        )
        filtered = self._apply_metadata_filters(fused, processed.filters)
        results = filtered[:top_k]
        if trace is not None:
            trace.record_stage(
                "hybrid_search",
                method="HybridSearch",
                details={
                    "top_k": top_k,
                    "dense_count": len(dense_results),
                    "sparse_count": len(sparse_results),
                    "fusion_count": len(fused),
                    "result_count": len(results),
                    "filters": dict(processed.filters),
                    "dense_failed": dense_error is not None,
                    "sparse_failed": sparse_error is not None,
                },
            )
        return results

    def _apply_metadata_filters(
        self,
        candidates: list[RetrievalResult],
        filters: dict[str, Any] | None,
    ) -> list[RetrievalResult]:
        """Filter fused candidates by metadata as a defensive fallback."""
        if filters is None or not filters:
            return candidates
        if not isinstance(filters, dict):
            raise HybridSearchError("filters must be a dictionary")
        return [
            candidate
            for candidate in candidates
            if all(candidate.metadata.get(key) == value for key, value in filters.items())
        ]

    def _run_route(
        self,
        stage_name: str,
        method: str,
        route: Callable[[], list[RetrievalResult]],
        trace: Any | None = None,
    ) -> tuple[list[RetrievalResult], Exception | None]:
        with ThreadPoolExecutor(max_workers=1) as executor:
            start = time.perf_counter()
            future = executor.submit(route)
            try:
                results = future.result()
                _record_timed_stage(
                    trace,
                    stage_name,
                    method=method,
                    started_at=start,
                    details={"result_count": len(results), "failed": False},
                )
                return results, None
            except Exception as exc:  # noqa: BLE001 - route failures degrade gracefully.
                _record_timed_stage(
                    trace,
                    stage_name,
                    method=method,
                    started_at=start,
                    details={
                        "result_count": 0,
                        "failed": True,
                        "error": exc.__class__.__name__,
                    },
                )
                return [], exc


def _retrieval_top_k(settings: Any | None, field_name: str, default: int) -> int:
    retrieval = getattr(settings, "retrieval", None)
    value = int(getattr(retrieval, field_name, default))
    return value if value > 0 else default


def _record_timed_stage(
    trace: Any | None,
    stage_name: str,
    method: str,
    started_at: float,
    details: dict[str, Any],
) -> None:
    if trace is not None:
        trace.record_stage(
            stage_name,
            method=method,
            details=details,
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
        )
