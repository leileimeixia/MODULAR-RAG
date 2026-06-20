"""Cross-encoder style reranker with injectable scorer."""

from __future__ import annotations

import re
from typing import Any, Protocol

from core.settings import RerankSettings

from .base_reranker import BaseReranker, RerankCandidate, RerankResult


class CrossEncoderScorer(Protocol):
    """Minimal scorer protocol for cross-encoder implementations."""

    def score(self, query: str, text: str) -> float:
        """Return a relevance score for a query/text pair."""


class CrossEncoderRerankerError(ValueError):
    """Raised when cross-encoder reranking cannot score candidates."""


class LexicalOverlapScorer:
    """Deterministic fallback scorer based on normalized token overlap."""

    def score(self, query: str, text: str) -> float:
        query_tokens = set(_tokenize(query))
        text_tokens = set(_tokenize(text))
        if not query_tokens or not text_tokens:
            return 0.0
        return len(query_tokens & text_tokens) / len(query_tokens)


class CrossEncoderReranker(BaseReranker):
    """Score each candidate with a cross-encoder-like scorer and sort descending."""

    def __init__(
        self,
        settings: RerankSettings,
        scorer: CrossEncoderScorer | None = None,
    ) -> None:
        self.settings = settings
        self.scorer = scorer or LexicalOverlapScorer()

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int | None = None,
        trace: Any | None = None,
    ) -> list[RerankResult]:
        """Return candidates ordered by scorer output."""
        if not query:
            raise CrossEncoderRerankerError("query must not be empty")
        if not candidates:
            return []

        limit = top_k if top_k is not None else self.settings.top_k
        if limit < 0:
            raise CrossEncoderRerankerError("top_k must be greater than or equal to 0")
        if limit == 0:
            return []

        scored: list[tuple[RerankCandidate, float]] = []
        for candidate in candidates:
            try:
                score = self.scorer.score(query, candidate.text)
            except TimeoutError as exc:
                raise CrossEncoderRerankerError(
                    "cross-encoder scorer timed out"
                ) from exc
            except Exception as exc:
                raise CrossEncoderRerankerError(
                    f"cross-encoder scorer failed: {exc.__class__.__name__}"
                ) from exc

            if not isinstance(score, int | float):
                raise CrossEncoderRerankerError(
                    f"cross-encoder scorer returned non-numeric score for {candidate.id}"
                )
            scored.append((candidate, float(score)))

        ranked = sorted(scored, key=lambda item: (-item[1], item[0].id))
        return [
            RerankResult(
                id=candidate.id,
                text=candidate.text,
                score=score,
                metadata=candidate.metadata,
            )
            for candidate, score in ranked[:limit]
        ]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+", text.lower())
