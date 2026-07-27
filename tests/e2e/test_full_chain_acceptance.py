"""Offline full-chain acceptance checks for the project entrypoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import RetrievalResult
from ingestion import IngestionResult
from libs.evaluator import BaseEvaluator, EvaluationResult
from scripts import evaluate as evaluate_cli
from scripts import ingest as ingest_cli
from scripts import query as query_cli


@dataclass(frozen=True)
class FakeSettings:
    retrieval: Any = None


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def run(
        self,
        path: str | Path,
        collection: str = "default",
        force: bool = False,
    ) -> IngestionResult:
        self.calls.append(Path(path))
        return IngestionResult(
            file_hash=f"hash-{len(self.calls)}",
            document_id=f"doc-{len(self.calls)}",
            skipped=False,
            chunk_count=1,
            record_count=1,
            vector_ids=[f"chunk-{len(self.calls)}"],
            image_count=0,
            trace=None,
        )


class FakeHybridSearch:
    def search(self, query: str, top_k: int, filters=None, trace=None):
        if trace is not None:
            trace.record_stage("hybrid_search", method="FakeHybridSearch")
        return [
            RetrievalResult(
                chunk_id="chunk-1",
                score=0.9,
                text=f"retrieved context for {query}",
                metadata={"source_path": "tests/fixtures/sample_documents/sample.md"},
            )
        ][:top_k]


class FakeReranker:
    def rerank(self, query: str, candidates, top_k: int | None = None, trace=None):
        if trace is not None:
            trace.record_stage("rerank", method="FakeReranker")
        return list(candidates)[: top_k or len(candidates)]


class FakeEvaluator(BaseEvaluator):
    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        hit = bool(set(retrieved_ids) & set(golden_ids))
        return EvaluationResult(metrics={"hit_rate": 1.0 if hit else 0.0})


def test_offline_full_chain_acceptance(monkeypatch, tmp_path, capsys) -> None:
    """Verify the reproducible chain: ingest -> query -> evaluate."""
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("evaluation:\n  provider: custom\n", encoding="utf-8")
    monkeypatch.setattr(ingest_cli, "load_settings", lambda path: FakeSettings())
    monkeypatch.setattr(query_cli, "load_settings", lambda path: FakeSettings())
    monkeypatch.setattr(evaluate_cli, "load_settings", lambda path: FakeSettings())

    pipeline = FakePipeline()
    ingest_exit = ingest_cli.main(
        [
            "--path",
            "tests/fixtures/sample_documents",
            "--collection",
            "acceptance",
            "--force",
            "--settings",
            str(settings_path),
        ],
        pipeline_factory=lambda settings: pipeline,
    )
    ingest_output = capsys.readouterr().out
    assert ingest_exit == 0
    assert [path.name for path in pipeline.calls] == ["sample.md", "simple.pdf"]
    assert "Summary: ingested=2 skipped=0 total=2" in ingest_output

    query_exit = query_cli.main(
        [
            "--query",
            "sample project document",
            "--top-k",
            "1",
            "--verbose",
            "--settings",
            str(settings_path),
        ],
        hybrid_search_factory=lambda settings: FakeHybridSearch(),
        reranker_factory=lambda settings: FakeReranker(),
    )
    query_output = capsys.readouterr().out
    assert query_exit == 0
    assert "chunk-1" in query_output
    assert "Trace:" in query_output

    test_set = tmp_path / "golden_test_set.json"
    test_set.write_text(
        json.dumps(
            {
                "test_cases": [
                    {
                        "query": "sample project document",
                        "expected_chunk_ids": ["chunk-1"],
                        "generated_answer": "The sample document was retrieved.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    evaluate_exit = evaluate_cli.main(
        [
            "--test-set",
            str(test_set),
            "--settings",
            str(settings_path),
            "--top-k",
            "1",
        ],
        hybrid_search_factory=lambda settings: FakeHybridSearch(),
        evaluator_factory=lambda settings: FakeEvaluator(),
    )
    evaluate_payload = json.loads(capsys.readouterr().out)
    assert evaluate_exit == 0
    assert evaluate_payload["metrics"] == {"hit_rate": 1.0}
    assert evaluate_payload["case_results"][0]["retrieved_ids"] == ["chunk-1"]
