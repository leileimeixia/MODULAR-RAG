"""Dashboard service for running golden test set evaluations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.query_engine import HybridSearch
from core.settings import load_settings
from libs.evaluator import EvaluatorFactory
from observability.evaluation import EvalRunner


class EvaluationService:
    """Run evaluation reports for the dashboard."""

    def __init__(self, settings_path: str | Path = "config/settings.yaml") -> None:
        self.settings_path = Path(settings_path)

    def run_evaluation(
        self,
        test_set_path: str | Path,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Run an EvalRunner report and return a display-ready dictionary."""
        settings = load_settings(self.settings_path)
        report = EvalRunner(
            settings=settings,
            hybrid_search=HybridSearch(settings=settings),
            evaluator=EvaluatorFactory.create(settings),
            top_k=top_k,
        ).run(test_set_path)
        return report.to_dict()
