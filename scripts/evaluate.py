"""Run golden test set evaluation from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.query_engine import HybridSearch
from core.settings import load_settings
from libs.evaluator import EvaluatorFactory
from observability.evaluation import EvalRunner


HybridSearchFactory = Callable[[Any], HybridSearch]
EvaluatorFactoryFunc = Callable[[Any], Any]


def main(
    argv: Sequence[str] | None = None,
    hybrid_search_factory: HybridSearchFactory | None = None,
    evaluator_factory: EvaluatorFactoryFunc | None = None,
) -> int:
    """Parse CLI args, run evaluation, and return a process exit code."""
    args = _parse_args(argv)
    try:
        settings = load_settings(args.settings)
        hybrid_search = (
            hybrid_search_factory(settings)
            if hybrid_search_factory is not None
            else HybridSearch(settings=settings)
        )
        evaluator = (
            evaluator_factory(settings)
            if evaluator_factory is not None
            else EvaluatorFactory.create(settings)
        )
        report = EvalRunner(
            settings=settings,
            hybrid_search=hybrid_search,
            evaluator=evaluator,
            top_k=args.top_k,
        ).run(args.test_set)
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality.")
    parser.add_argument(
        "--test-set",
        default=str(PROJECT_ROOT / "tests" / "fixtures" / "golden_test_set.json"),
        help="Path to golden_test_set.json.",
    )
    parser.add_argument(
        "--settings",
        default=str(PROJECT_ROOT / "config" / "settings.yaml"),
        help="Path to settings.yaml.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override retrieval top_k for all cases.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
