"""Core reranker orchestration with fallback handling."""

from __future__ import annotations

from typing import Any

from core import RetrievalResult
from libs.reranker import BaseReranker, RerankCandidate, RerankResult, RerankerFactory


class CoreRerankerError(ValueError):
    """Raised when rerank input cannot be handled."""


class CoreReranker:
    """Adapt RetrievalResult candidates to libs rerankers and fallback on failure."""

    def __init__(
        self,
        settings: Any | None = None,
        backend: BaseReranker | None = None,
    ) -> None:
        self.settings = settings
        self.backend = backend or RerankerFactory.create(settings)

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int | None = None,
        trace: Any | None = None,
    ) -> list[RetrievalResult]:
        """Return reranked candidates, falling back to incoming order on backend errors."""
        if not isinstance(query, str) or not query.strip():
            raise CoreRerankerError("query must be a non-empty string")
        _validate_candidates(candidates)
        limit = _resolve_top_k(top_k, self.settings)
        if limit < 0:
            raise CoreRerankerError("top_k must be greater than or equal to 0")
        if limit == 0 or not candidates:
            self._record_trace(trace, limit, len(candidates), 0, fallback=False)
            return []

        try:
            rerank_results = self.backend.rerank(
                query.strip(),
                _to_rerank_candidates(candidates),
                top_k=limit,
                trace=trace,
            )
            results = _to_retrieval_results(rerank_results)
            self._record_trace(trace, limit, len(candidates), len(results), fallback=False)
            return results
        except Exception as exc:  # noqa: BLE001 - rerank failure should degrade safely.
            fallback_results = candidates[:limit]
            self._record_trace(
                trace,
                limit,
                len(candidates),
                len(fallback_results),
                fallback=True,
                error=exc,
            )
            return fallback_results

    def _record_trace(
        self,
        trace: Any | None,
        top_k: int,
        candidate_count: int,
        result_count: int,
        fallback: bool,
        error: Exception | None = None,
    ) -> None:
        if trace is not None:
            details: dict[str, Any] = {
                "top_k": top_k,
                "candidate_count": candidate_count,
                "result_count": result_count,
                "fallback": fallback,
                "backend": self.backend.__class__.__name__,
            }
            if error is not None:
                details["error"] = error.__class__.__name__
            trace.record_stage("rerank", method="CoreReranker", details=details)


def _resolve_top_k(top_k: int | None, settings: Any | None) -> int:
    if top_k is not None:
        return top_k
    rerank_settings = getattr(settings, "rerank", None)
    return int(getattr(rerank_settings, "top_k", 0))


def _validate_candidates(candidates: list[RetrievalResult]) -> None:
    if not isinstance(candidates, list):
        raise CoreRerankerError("candidates must be a list")
    if not all(isinstance(candidate, RetrievalResult) for candidate in candidates):
        raise CoreRerankerError("candidates must contain only RetrievalResult objects")


def _to_rerank_candidates(candidates: list[RetrievalResult]) -> list[RerankCandidate]:
    return [
        RerankCandidate(
            id=candidate.chunk_id,
            text=candidate.text,
            score=candidate.score,
            metadata=dict(candidate.metadata),
        )
        for candidate in candidates
    ]


def _to_retrieval_results(results: list[RerankResult]) -> list[RetrievalResult]:
    return [
        RetrievalResult(
            chunk_id=result.id,
            text=result.text,
            score=result.score,
            metadata=dict(result.metadata),
        )
        for result in results
    ]
