"""Tests for evaluation CLI wrapper."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core import RetrievalResult
from libs.evaluator import BaseEvaluator, EvaluationResult
from scripts import evaluate as evaluate_cli


@dataclass(frozen=True)
class FakeRetrievalSettings:
    fusion_top_k: int = 3


@dataclass(frozen=True)
class FakeSettings:
    retrieval: FakeRetrievalSettings = FakeRetrievalSettings()


class FakeHybridSearch:
    def search(self, query: str, top_k: int, filters=None):
        return [
            RetrievalResult(
                chunk_id="chunk-a",
                score=1.0,
                text=query,
                metadata={"source_path": "docs/a.md"},
            )
        ]


class FakeEvaluator(BaseEvaluator):
    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        return EvaluationResult(metrics={"hit_rate": 1.0})


def test_evaluate_cli_prints_eval_report(monkeypatch, tmp_path, capsys) -> None:
    test_set = tmp_path / "golden_test_set.json"
    test_set.write_text(
        json.dumps(
            {
                "test_cases": [
                    {
                        "query": "alpha?",
                        "expected_chunk_ids": ["chunk-a"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluate_cli, "load_settings", lambda path: FakeSettings())

    exit_code = evaluate_cli.main(
        ["--test-set", str(test_set), "--settings", "settings.yaml"],
        hybrid_search_factory=lambda settings: FakeHybridSearch(),
        evaluator_factory=lambda settings: FakeEvaluator(),
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["metrics"] == {"hit_rate": 1.0}
    assert payload["case_results"][0]["retrieved_ids"] == ["chunk-a"]


def test_evaluate_cli_reports_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(evaluate_cli, "load_settings", lambda path: FakeSettings())

    exit_code = evaluate_cli.main(
        ["--test-set", "missing.json"],
        hybrid_search_factory=lambda settings: FakeHybridSearch(),
        evaluator_factory=lambda settings: FakeEvaluator(),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Evaluation failed:" in captured.err
