"""Rule-based query preprocessing for retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DEFAULT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
FILTER_KEYS = {"collection", "doc_type", "language", "access_level", "source_path"}


class QueryProcessorError(ValueError):
    """Raised when a query cannot be processed."""


@dataclass(frozen=True)
class ProcessedQuery:
    """Normalized query payload shared by retrieval components."""

    query: str
    keywords: list[str]
    filters: dict[str, Any] = field(default_factory=dict)


class QueryProcessor:
    """Extract keywords and lightweight metadata filters from a raw query."""

    def __init__(
        self,
        stopwords: set[str] | None = None,
        filter_keys: set[str] | None = None,
    ) -> None:
        self.stopwords = {word.lower() for word in (stopwords or DEFAULT_STOPWORDS)}
        self.filter_keys = {key.lower() for key in (filter_keys or FILTER_KEYS)}

    def process(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        trace: Any | None = None,
    ) -> ProcessedQuery:
        """Return normalized keywords and merged filters for retrieval."""
        if not isinstance(query, str) or not query.strip():
            raise QueryProcessorError("query must be a non-empty string")
        if filters is not None and not isinstance(filters, dict):
            raise QueryProcessorError("filters must be a dictionary")

        inline_filters, query_without_filters = self._extract_inline_filters(query)
        merged_filters = {**inline_filters, **(filters or {})}
        keywords = self._extract_keywords(query_without_filters)
        if not keywords:
            keywords = self._extract_keywords(query, allow_stopwords=True)
        if not keywords:
            raise QueryProcessorError("query must contain at least one keyword")

        processed = ProcessedQuery(
            query=query.strip(),
            keywords=keywords,
            filters=merged_filters,
        )
        if trace is not None:
            trace.record_stage(
                "query_processing",
                method="rule",
                details={
                    "keyword_count": len(processed.keywords),
                    "filter_keys": sorted(processed.filters),
                },
            )
        return processed

    def _extract_inline_filters(self, query: str) -> tuple[dict[str, str], str]:
        filters: dict[str, str] = {}

        def replace(match: re.Match[str]) -> str:
            key = match.group("key").lower()
            value = (match.group("quoted") or match.group("bare") or "").strip()
            if key not in self.filter_keys or not value:
                return match.group(0)
            filters[key] = value
            return " "

        cleaned = re.sub(
            r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:\"(?P<quoted>[^\"]+)\"|(?P<bare>[^\s]+))",
            replace,
            query,
        )
        return filters, cleaned

    def _extract_keywords(self, query: str, allow_stopwords: bool = False) -> list[str]:
        keywords: list[str] = []
        for token in _tokenize(query):
            if not allow_stopwords and token in self.stopwords:
                continue
            if token not in keywords:
                keywords.append(token)
        return keywords


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in re.finditer(r"\w+", text)]
