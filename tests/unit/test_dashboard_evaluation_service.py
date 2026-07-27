"""Tests for dashboard evaluation service wiring."""

from __future__ import annotations

from dataclasses import dataclass

from observability.dashboard.services import evaluation_service as service_module
from observability.dashboard.services.evaluation_service import EvaluationService


@dataclass(frozen=True)
class FakeSettings:
    name: str = "settings"


class FakeHybridSearch:
    def __init__(self, settings) -> None:
        self.settings = settings


class FakeEvaluator:
    pass


class FakeReport:
    def to_dict(self):
        return {
            "metrics": {"hit_rate": 1.0},
            "case_results": [],
            "details": {"case_count": 0},
        }


class FakeEvalRunner:
    calls: list[dict] = []

    def __init__(self, settings, hybrid_search, evaluator, top_k=None) -> None:
        self.settings = settings
        self.hybrid_search = hybrid_search
        self.evaluator = evaluator
        self.top_k = top_k

    def run(self, test_set_path):
        self.__class__.calls.append(
            {
                "settings": self.settings,
                "hybrid_search": self.hybrid_search,
                "evaluator": self.evaluator,
                "top_k": self.top_k,
                "test_set_path": test_set_path,
            }
        )
        return FakeReport()


def test_evaluation_service_runs_eval_runner(monkeypatch) -> None:
    settings = FakeSettings()
    evaluator = FakeEvaluator()
    FakeEvalRunner.calls = []
    monkeypatch.setattr(service_module, "load_settings", lambda path: settings)
    monkeypatch.setattr(service_module, "HybridSearch", FakeHybridSearch)
    monkeypatch.setattr(
        service_module.EvaluatorFactory,
        "create",
        lambda loaded_settings: evaluator,
    )
    monkeypatch.setattr(service_module, "EvalRunner", FakeEvalRunner)

    result = EvaluationService(settings_path="settings.yaml").run_evaluation(
        "golden.json",
        top_k=3,
    )

    assert result["metrics"] == {"hit_rate": 1.0}
    assert FakeEvalRunner.calls[0]["settings"] == settings
    assert FakeEvalRunner.calls[0]["hybrid_search"].settings == settings
    assert FakeEvalRunner.calls[0]["evaluator"] == evaluator
    assert FakeEvalRunner.calls[0]["top_k"] == 3
    assert FakeEvalRunner.calls[0]["test_set_path"] == "golden.json"
