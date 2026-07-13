"""Rank fusion for dense and sparse retrieval results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import RetrievalResult


class RRFusionError(ValueError):
    """Raised when retrieval results cannot be fused."""


@dataclass
class _FusionEntry:
    result: RetrievalResult
    score: float = 0.0
    best_rank: int = 0
    routes: int = 0


class RRFusion:
    """Fuse ranked retrieval lists with reciprocal rank fusion."""

    def __init__(self, settings: Any | None = None, rrf_k: int | None = None) -> None:
        configured_k = _settings_rrf_k(settings)
        self.rrf_k = rrf_k if rrf_k is not None else configured_k
        if self.rrf_k <= 0:
            raise RRFusionError("rrf_k must be greater than 0")

    def fuse(
        self,
        dense_results: list[RetrievalResult],
        sparse_results: list[RetrievalResult],
        top_k: int,
        trace: Any | None = None,
    ) -> list[RetrievalResult]:
        """Return a deterministic RRF ranking for dense and sparse results."""
        _validate_results(dense_results, "dense_results")
        _validate_results(sparse_results, "sparse_results")
        if top_k <= 0:
            raise RRFusionError("top_k must be greater than 0")

        entries: dict[str, _FusionEntry] = {}
        self._accumulate(entries, dense_results)
        self._accumulate(entries, sparse_results)

        ranked = sorted(
            entries.values(),
            key=lambda entry: (-entry.score, entry.best_rank, entry.result.chunk_id),
        )
        fused_results = [
            RetrievalResult(
                chunk_id=entry.result.chunk_id,
                score=entry.score,
                text=entry.result.text,
                metadata=dict(entry.result.metadata),
            )
            for entry in ranked[:top_k]
        ]
        if trace is not None:
            trace.record_stage(
                "rrf_fusion",
                method="RRFusion",
                details={
                    "rrf_k": self.rrf_k,
                    "top_k": top_k,
                    "dense_count": len(dense_results),
                    "sparse_count": len(sparse_results),
                    "result_count": len(fused_results),
                },
            )
        return fused_results

    def _accumulate(
        self,
        entries: dict[str, _FusionEntry],
        results: list[RetrievalResult],
    ) -> None:
        seen_in_route: set[str] = set()
        for index, result in enumerate(results, start=1):
            if result.chunk_id in seen_in_route:
                continue
            seen_in_route.add(result.chunk_id)
            entry = entries.setdefault(
                result.chunk_id,
                _FusionEntry(result=result, best_rank=index),
            )
            entry.score += 1.0 / (self.rrf_k + index)
            entry.best_rank = min(entry.best_rank or index, index)
            entry.routes += 1


def _settings_rrf_k(settings: Any | None) -> int:
    retrieval = getattr(settings, "retrieval", None)
    return int(getattr(retrieval, "rrf_k", 60))


def _validate_results(results: list[RetrievalResult], label: str) -> None:
    if not isinstance(results, list):
        raise RRFusionError(f"{label} must be a list")
    if not all(isinstance(result, RetrievalResult) for result in results):
        raise RRFusionError(f"{label} must contain only RetrievalResult objects")
