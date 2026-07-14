"""Tests for the query CLI wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from core import RetrievalResult
from scripts import query as query_cli


@dataclass(frozen=True)
class FakeSettings:
    name: str = "settings"


class FakeHybridSearch:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query: str, top_k: int, filters=None, trace=None):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "filters": filters or {},
                "trace_enabled": trace is not None,
            }
        )
        if trace is not None:
            trace.record_stage("hybrid_search", method="FakeHybridSearch")
        return [
            RetrievalResult(
                chunk_id="chunk-a",
                score=0.5,
                text="alpha result",
                metadata={"source_path": "docs/a.md"},
            )
        ]


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def rerank(self, query: str, candidates, top_k: int | None = None, trace=None):
        self.calls.append(
            {
                "query": query,
                "candidate_ids": [candidate.chunk_id for candidate in candidates],
                "top_k": top_k,
                "trace_enabled": trace is not None,
            }
        )
        if trace is not None:
            trace.record_stage("rerank", method="FakeReranker")
        return [
            RetrievalResult(
                chunk_id="chunk-reranked",
                score=0.9,
                text="reranked result",
                metadata={"source_path": "docs/r.md"},
            )
        ]


def test_query_cli_runs_hybrid_search_and_reranker(monkeypatch, capsys) -> None:
    hybrid = FakeHybridSearch()
    reranker = FakeReranker()
    monkeypatch.setattr(query_cli, "load_settings", lambda path: FakeSettings())

    exit_code = query_cli.main(
        ["--query", "alpha", "--top-k", "3", "--filter", "collection=docs"],
        hybrid_search_factory=lambda settings: hybrid,
        reranker_factory=lambda settings: reranker,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert hybrid.calls == [
        {
            "query": "alpha",
            "top_k": 3,
            "filters": {"collection": "docs"},
            "trace_enabled": False,
        }
    ]
    assert reranker.calls == [
        {
            "query": "alpha",
            "candidate_ids": ["chunk-a"],
            "top_k": 3,
            "trace_enabled": False,
        }
    ]
    assert "chunk-reranked" in captured.out
    assert "docs/r.md" in captured.out


def test_query_cli_can_skip_rerank(monkeypatch, capsys) -> None:
    hybrid = FakeHybridSearch()
    reranker = FakeReranker()
    monkeypatch.setattr(query_cli, "load_settings", lambda path: FakeSettings())

    exit_code = query_cli.main(
        ["--query", "alpha", "--no-rerank"],
        hybrid_search_factory=lambda settings: hybrid,
        reranker_factory=lambda settings: reranker,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert reranker.calls == []
    assert "chunk-a" in captured.out


def test_query_cli_verbose_prints_trace(monkeypatch, capsys) -> None:
    hybrid = FakeHybridSearch()
    reranker = FakeReranker()
    monkeypatch.setattr(query_cli, "load_settings", lambda path: FakeSettings())

    exit_code = query_cli.main(
        ["--query", "alpha", "--verbose"],
        hybrid_search_factory=lambda settings: hybrid,
        reranker_factory=lambda settings: reranker,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Trace:" in captured.out
    assert "hybrid_search" in captured.out
    assert "rerank" in captured.out


def test_query_cli_reports_invalid_filter(monkeypatch, capsys) -> None:
    monkeypatch.setattr(query_cli, "load_settings", lambda path: FakeSettings())

    exit_code = query_cli.main(["--query", "alpha", "--filter", "bad-filter"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "filter must use key=value format" in captured.err
