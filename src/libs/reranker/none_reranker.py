"""No-op reranker implementation."""

from __future__ import annotations

from typing import Any

from core.settings import RerankSettings

from .base_reranker import BaseReranker, RerankCandidate, RerankResult


class NoneReranker(BaseReranker):
    """Return incoming candidates in their current order."""

    def __init__(self, settings: RerankSettings) -> None:
        self.settings = settings

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int | None = None,
        trace: Any | None = None,
    ) -> list[RerankResult]:
        limit = top_k if top_k is not None else self.settings.top_k
        if limit < 0:
            raise ValueError("top_k must be greater than or equal to 0")
        return [
            RerankResult(
                id=candidate.id,
                text=candidate.text,
                score=candidate.score,
                metadata=candidate.metadata,
            )
            for candidate in candidates[:limit]
        ]
