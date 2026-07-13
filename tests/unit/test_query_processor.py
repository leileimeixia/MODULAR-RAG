"""Tests for rule-based query preprocessing."""

from __future__ import annotations

import pytest

from core.query_engine import ProcessedQuery, QueryProcessor, QueryProcessorError
from core.trace import TraceContext


def test_query_processor_extracts_keywords_without_stopwords() -> None:
    processed = QueryProcessor().process("What is the modular RAG pipeline?")

    assert processed == ProcessedQuery(
        query="What is the modular RAG pipeline?",
        keywords=["what", "modular", "rag", "pipeline"],
        filters={},
    )


def test_query_processor_extracts_inline_filters() -> None:
    processed = QueryProcessor().process(
        'collection:docs doc_type:pdf language:"zh-CN" explain BM25 index'
    )

    assert processed.keywords == ["explain", "bm25", "index"]
    assert processed.filters == {
        "collection": "docs",
        "doc_type": "pdf",
        "language": "zh-CN",
    }


def test_query_processor_merges_external_filters_with_precedence() -> None:
    processed = QueryProcessor().process(
        "collection:docs alpha beta",
        filters={"collection": "override", "access_level": "internal"},
    )

    assert processed.keywords == ["alpha", "beta"]
    assert processed.filters == {
        "collection": "override",
        "access_level": "internal",
    }


def test_query_processor_keeps_unknown_colon_tokens_as_keywords() -> None:
    processed = QueryProcessor().process("author:jane retrieval")

    assert processed.keywords == ["author", "jane", "retrieval"]
    assert processed.filters == {}


def test_query_processor_falls_back_when_query_is_only_stopwords() -> None:
    processed = QueryProcessor().process("the and of")

    assert processed.keywords == ["the", "and", "of"]
    assert processed.filters == {}


def test_query_processor_supports_unicode_keywords() -> None:
    processed = QueryProcessor().process("检索 RAG 文档")

    assert processed.keywords == ["检索", "rag", "文档"]


def test_query_processor_rejects_blank_query() -> None:
    with pytest.raises(QueryProcessorError, match="non-empty"):
        QueryProcessor().process("  ")


def test_query_processor_rejects_non_dict_filters() -> None:
    with pytest.raises(QueryProcessorError, match="dictionary"):
        QueryProcessor().process("alpha", filters=["bad"])


def test_query_processor_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-query")

    processed = QueryProcessor().process("collection:docs alpha", trace=trace)

    assert processed.keywords == ["alpha"]
    assert trace.stages[-1].name == "query_processing"
    assert trace.stages[-1].method == "rule"
    assert trace.stages[-1].details == {
        "keyword_count": 1,
        "filter_keys": ["collection"],
    }
