"""Tests for the cross-encoder style reranker."""

from __future__ import annotations

import pytest

from core.settings import RerankSettings
from libs.reranker import (
    CrossEncoderReranker,
    CrossEncoderRerankerError,
    LexicalOverlapScorer,
    RerankCandidate,
    RerankResult,
    RerankerFactory,
)


class FakeScorer:
    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, str]] = []

    def score(self, query: str, text: str) -> float:
        self.calls.append((query, text))
        return self.scores[text]


class TimeoutScorer:
    def score(self, query: str, text: str) -> float:
        raise TimeoutError("too slow")


class BadScorer:
    def score(self, query: str, text: str):
        return "bad"


def _settings(top_k: int = 2) -> RerankSettings:
    return RerankSettings(
        enabled=True,
        provider="cross_encoder",
        model="mock-cross-encoder",
        top_k=top_k,
    )


def _candidates() -> list[RerankCandidate]:
    return [
        RerankCandidate(id="a", text="alpha text", score=0.1),
        RerankCandidate(id="b", text="beta text", score=0.2),
        RerankCandidate(id="c", text="gamma text", score=0.3),
    ]


def test_factory_creates_cross_encoder_reranker() -> None:
    reranker = RerankerFactory.create(_settings())

    assert isinstance(reranker, CrossEncoderReranker)


def test_cross_encoder_reranker_orders_by_injected_scorer() -> None:
    scorer = FakeScorer(
        {
            "alpha text": 0.4,
            "beta text": 0.9,
            "gamma text": 0.2,
        }
    )
    reranker = CrossEncoderReranker(_settings(top_k=3), scorer=scorer)

    results = reranker.rerank("query", _candidates())

    assert results == [
        RerankResult(id="b", text="beta text", score=0.9),
        RerankResult(id="a", text="alpha text", score=0.4),
        RerankResult(id="c", text="gamma text", score=0.2),
    ]
    assert scorer.calls == [
        ("query", "alpha text"),
        ("query", "beta text"),
        ("query", "gamma text"),
    ]


def test_cross_encoder_reranker_applies_top_k() -> None:
    scorer = FakeScorer(
        {
            "alpha text": 0.4,
            "beta text": 0.9,
            "gamma text": 0.2,
        }
    )
    reranker = CrossEncoderReranker(_settings(top_k=1), scorer=scorer)

    assert [result.id for result in reranker.rerank("query", _candidates())] == ["b"]


def test_lexical_overlap_scorer_is_deterministic_default() -> None:
    scorer = LexicalOverlapScorer()

    assert scorer.score("alpha missing", "alpha text") == 0.5
    assert scorer.score("missing", "alpha text") == 0.0


def test_cross_encoder_reranker_wraps_timeout_as_fallback_signal() -> None:
    reranker = CrossEncoderReranker(_settings(), scorer=TimeoutScorer())

    with pytest.raises(CrossEncoderRerankerError, match="timed out"):
        reranker.rerank("query", _candidates())


def test_cross_encoder_reranker_rejects_non_numeric_score() -> None:
    reranker = CrossEncoderReranker(_settings(), scorer=BadScorer())

    with pytest.raises(CrossEncoderRerankerError, match="non-numeric"):
        reranker.rerank("query", _candidates())


def test_cross_encoder_reranker_rejects_invalid_inputs() -> None:
    reranker = CrossEncoderReranker(_settings())

    with pytest.raises(CrossEncoderRerankerError, match="query must not be empty"):
        reranker.rerank("", _candidates())

    with pytest.raises(CrossEncoderRerankerError, match="top_k"):
        reranker.rerank("query", _candidates(), top_k=-1)
