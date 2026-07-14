"""Online query CLI for hybrid search and optional reranking."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core import RetrievalResult
from core.query_engine import CoreReranker, HybridSearch
from core.settings import load_settings
from core.trace import TraceContext


HybridSearchFactory = Callable[[Any], HybridSearch]
RerankerFactory = Callable[[Any], CoreReranker]


def main(
    argv: Sequence[str] | None = None,
    hybrid_search_factory: HybridSearchFactory | None = None,
    reranker_factory: RerankerFactory | None = None,
) -> int:
    """Parse CLI arguments, run query retrieval, and return a process exit code."""
    args = _parse_args(argv)
    try:
        filters = _parse_filters(args.filter)
        settings = load_settings(args.settings)
        trace = TraceContext() if args.verbose else None
        hybrid_search = (
            hybrid_search_factory(settings)
            if hybrid_search_factory is not None
            else HybridSearch(settings=settings)
        )
        candidates = hybrid_search.search(
            args.query,
            top_k=args.top_k,
            filters=filters,
            trace=trace,
        )
        results = candidates
        if not args.no_rerank:
            reranker = (
                reranker_factory(settings)
                if reranker_factory is not None
                else CoreReranker(settings=settings)
            )
            results = reranker.rerank(
                args.query,
                candidates,
                top_k=args.top_k,
                trace=trace,
            )
    except Exception as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1

    _print_results(results)
    if args.verbose and trace is not None:
        _print_trace(trace)
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the local RAG knowledge hub.")
    parser.add_argument("--query", required=True, help="Question or search text.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of final results to return. Defaults to 10.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Metadata filter as key=value. Can be passed multiple times.",
    )
    parser.add_argument(
        "--settings",
        default=str(PROJECT_ROOT / "config" / "settings.yaml"),
        help="Path to settings.yaml.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print trace stages for query processing and retrieval.",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip reranker and return fused retrieval results directly.",
    )
    return parser.parse_args(argv)


def _parse_filters(values: Sequence[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"filter must use key=value format: {value}")
        key, filter_value = value.split("=", 1)
        key = key.strip()
        filter_value = filter_value.strip()
        if not key or not filter_value:
            raise ValueError(f"filter must include non-empty key and value: {value}")
        filters[key] = filter_value
    return filters


def _print_results(results: list[RetrievalResult]) -> None:
    if not results:
        print("No results found.")
        return

    for index, result in enumerate(results, start=1):
        source = result.metadata.get("source_path", "-")
        print(f"[{index}] chunk_id={result.chunk_id} score={result.score:.6f}")
        print(f"source={source}")
        print(_preview(result.text))
        print()


def _preview(text: str, limit: int = 500) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _print_trace(trace: TraceContext) -> None:
    print("Trace:")
    print(f"trace_id={trace.trace_id}")
    for stage in trace.stages:
        print(f"- {stage.name} method={stage.method} details={stage.details}")


if __name__ == "__main__":
    raise SystemExit(main())
