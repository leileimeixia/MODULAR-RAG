"""Tests for the LLM-backed reranker."""

from __future__ import annotations

import json

import pytest

from core.settings import RerankSettings
from libs.reranker import (
    LLMReranker,
    LLMRerankerError,
    RerankCandidate,
    RerankResult,
    RerankerFactory,
)


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[dict[str, str]] | None = None

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return self.response


def _settings(top_k: int = 2) -> RerankSettings:
    return RerankSettings(
        enabled=True,
        provider="llm",
        model="mock-reranker",
        top_k=top_k,
    )


def _candidates() -> list[RerankCandidate]:
    return [
        RerankCandidate(id="a", text="alpha text", score=0.1),
        RerankCandidate(id="b", text="beta text", score=0.2),
        RerankCandidate(id="c", text="gamma text", score=0.3),
    ]


def test_factory_creates_llm_reranker() -> None:
    reranker = RerankerFactory.create(_settings())

    assert isinstance(reranker, LLMReranker)


def test_llm_reranker_orders_by_structured_ranked_ids() -> None:
    llm = FakeLLM(json.dumps({"ranked_ids": ["b", "a"]}))
    reranker = LLMReranker(
        _settings(top_k=3),
        llm=llm,
        prompt_template="Rank by relevance.",
    )

    results = reranker.rerank("query", _candidates())

    assert results == [
        RerankResult(id="b", text="beta text", score=3.0),
        RerankResult(id="a", text="alpha text", score=2.0),
        RerankResult(id="c", text="gamma text", score=1.0),
    ]
    assert llm.messages is not None
    assert "Rank by relevance." in llm.messages[1]["content"]
    assert '"id": "a"' in llm.messages[1]["content"]


def test_llm_reranker_applies_top_k() -> None:
    llm = FakeLLM(json.dumps({"ranked_ids": ["c", "b", "a"]}))
    reranker = LLMReranker(
        _settings(top_k=2),
        llm=llm,
        prompt_template="Rank.",
    )

    assert [result.id for result in reranker.rerank("query", _candidates())] == [
        "c",
        "b",
    ]


def test_llm_reranker_requires_injected_llm_for_runtime_call() -> None:
    reranker = LLMReranker(_settings(), prompt_template="Rank.")

    with pytest.raises(LLMRerankerError, match="requires an injected LLM client"):
        reranker.rerank("query", _candidates())


def test_llm_reranker_rejects_invalid_json() -> None:
    reranker = LLMReranker(
        _settings(),
        llm=FakeLLM("not-json"),
        prompt_template="Rank.",
    )

    with pytest.raises(LLMRerankerError, match="valid JSON"):
        reranker.rerank("query", _candidates())


def test_llm_reranker_rejects_invalid_schema() -> None:
    reranker = LLMReranker(
        _settings(),
        llm=FakeLLM(json.dumps({"ids": ["a"]})),
        prompt_template="Rank.",
    )

    with pytest.raises(LLMRerankerError, match="ranked_ids"):
        reranker.rerank("query", _candidates())


def test_llm_reranker_rejects_unknown_ids() -> None:
    reranker = LLMReranker(
        _settings(),
        llm=FakeLLM(json.dumps({"ranked_ids": ["missing"]})),
        prompt_template="Rank.",
    )

    with pytest.raises(LLMRerankerError, match="unknown candidate ids"):
        reranker.rerank("query", _candidates())
