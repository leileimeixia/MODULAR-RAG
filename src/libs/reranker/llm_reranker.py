"""LLM-backed reranker implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from core.settings import RerankSettings

from .base_reranker import BaseReranker, RerankCandidate, RerankResult


class ChatClient(Protocol):
    """Minimal chat client protocol required by LLMReranker."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return assistant text for chat messages."""


class LLMRerankerError(ValueError):
    """Raised when LLM reranking cannot produce valid ranked ids."""


class LLMReranker(BaseReranker):
    """Rerank candidates by asking an injected LLM for structured ids."""

    def __init__(
        self,
        settings: RerankSettings,
        llm: ChatClient | None = None,
        prompt_path: str | Path = "config/prompts/rerank.txt",
        prompt_template: str | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.prompt_path = Path(prompt_path)
        self.prompt_template = (
            prompt_template if prompt_template is not None else self._load_prompt()
        )

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int | None = None,
        trace: Any | None = None,
    ) -> list[RerankResult]:
        """Return candidates ordered by ids produced by the LLM."""
        if not query:
            raise LLMRerankerError("query must not be empty")
        if not candidates:
            return []

        limit = top_k if top_k is not None else self.settings.top_k
        if limit < 0:
            raise LLMRerankerError("top_k must be greater than or equal to 0")
        if limit == 0:
            return []

        if self.llm is None:
            raise LLMRerankerError("LLMReranker requires an injected LLM client")

        prompt = self._build_prompt(query, candidates, limit)
        response = self.llm.chat(
            [
                {
                    "role": "system",
                    "content": "You rank candidate chunks and return JSON only.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        ranked_ids = _parse_ranked_ids(response)
        return _rank_candidates(candidates, ranked_ids, limit)

    def _load_prompt(self) -> str:
        if not self.prompt_path.exists():
            raise LLMRerankerError(f"rerank prompt not found: {self.prompt_path}")
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def _build_prompt(
        self,
        query: str,
        candidates: list[RerankCandidate],
        limit: int,
    ) -> str:
        candidate_payload = [
            {
                "id": candidate.id,
                "text": candidate.text,
                "score": candidate.score,
                "metadata": candidate.metadata,
            }
            for candidate in candidates
        ]
        return (
            f"{self.prompt_template}\n\n"
            "Return JSON with this exact shape: "
            '{"ranked_ids": ["candidate-id"]}\n\n'
            f"Query: {query}\n"
            f"Top K: {limit}\n"
            f"Candidates: {json.dumps(candidate_payload, ensure_ascii=False)}"
        )


def _parse_ranked_ids(response: str) -> list[str]:
    try:
        payload = json.loads(response)
    except json.JSONDecodeError as exc:
        raise LLMRerankerError("LLM reranker response must be valid JSON") from exc

    ranked_ids = payload.get("ranked_ids")
    if not isinstance(ranked_ids, list) or not all(
        isinstance(item, str) for item in ranked_ids
    ):
        raise LLMRerankerError(
            "LLM reranker response must include ranked_ids as a list of strings"
        )
    return ranked_ids


def _rank_candidates(
    candidates: list[RerankCandidate],
    ranked_ids: list[str],
    limit: int,
) -> list[RerankResult]:
    by_id = {candidate.id: candidate for candidate in candidates}
    unknown_ids = [candidate_id for candidate_id in ranked_ids if candidate_id not in by_id]
    if unknown_ids:
        raise LLMRerankerError(
            f"LLM reranker returned unknown candidate ids: {', '.join(unknown_ids)}"
        )

    ranked: list[RerankCandidate] = []
    seen: set[str] = set()
    for candidate_id in ranked_ids:
        if candidate_id in seen:
            continue
        ranked.append(by_id[candidate_id])
        seen.add(candidate_id)

    for candidate in candidates:
        if candidate.id not in seen:
            ranked.append(candidate)

    return [
        RerankResult(
            id=candidate.id,
            text=candidate.text,
            score=float(len(ranked) - index),
            metadata=candidate.metadata,
        )
        for index, candidate in enumerate(ranked[:limit])
    ]
