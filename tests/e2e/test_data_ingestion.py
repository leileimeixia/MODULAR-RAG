"""E2E-style tests for the offline ingestion CLI."""

from __future__ import annotations

from pathlib import Path

from core import Document
from ingestion import IngestionResult
from scripts import ingest


class FakePipeline:
    def __init__(self, skip_second: bool = False) -> None:
        self.skip_second = skip_second
        self.calls: list[dict] = []

    def run(
        self,
        path: str | Path,
        collection: str = "default",
        force: bool = False,
    ) -> IngestionResult:
        self.calls.append({"path": Path(path), "collection": collection, "force": force})
        skipped = self.skip_second and len(self.calls) == 2
        return IngestionResult(
            file_hash=f"hash-{len(self.calls)}",
            document_id=None if skipped else f"doc-{len(self.calls)}",
            skipped=skipped,
            chunk_count=0 if skipped else 2,
            record_count=0 if skipped else 2,
            vector_ids=[] if skipped else [f"chunk-{len(self.calls)}"],
            image_count=0,
            trace=None,
        )


def _settings_file(tmp_path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        """
llm:
  provider: openai
  model: gpt-5.5
  api_key: test
embedding:
  provider: openai
  model: text-embedding-ada-002
  dimensions: 1536
  api_key: test
vision_llm:
  enabled: false
  provider: openai
  model: gpt-4o
  api_key: test
  max_image_size: 2048
vector_store:
  provider: chroma
  persist_directory: ./tmp/chroma
  collection_name: test
retrieval:
  dense_top_k: 20
  sparse_top_k: 20
  fusion_top_k: 10
  rrf_k: 60
splitter:
  provider: recursive
  chunk_size: 1000
  chunk_overlap: 200
rerank:
  enabled: false
  provider: none
evaluation:
  enabled: false
  provider: custom
observability:
  log_level: INFO
  trace_enabled: true
  trace_file: ./tmp/traces.jsonl
""".strip(),
        encoding="utf-8",
    )
    return path


def test_ingest_cli_runs_pipeline_for_single_file(tmp_path, capsys) -> None:
    source = tmp_path / "sample.md"
    source.write_text("# Sample", encoding="utf-8")
    pipeline = FakePipeline()

    exit_code = ingest.main(
        [
            "--path",
            str(source),
            "--collection",
            "docs",
            "--force",
            "--settings",
            str(_settings_file(tmp_path)),
        ],
        pipeline_factory=lambda settings: pipeline,
    )

    assert exit_code == 0
    assert pipeline.calls == [{"path": source, "collection": "docs", "force": True}]
    assert "INGESTED document=doc-1 chunks=2 records=2 images=0" in capsys.readouterr().out


def test_ingest_cli_runs_supported_files_in_directory(tmp_path, capsys) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    first = docs / "a.md"
    second = docs / "b.pdf"
    ignored = docs / "ignored.bin"
    first.write_text("a", encoding="utf-8")
    second.write_bytes(b"%PDF")
    ignored.write_bytes(b"ignored")
    pipeline = FakePipeline(skip_second=True)

    exit_code = ingest.main(
        ["--path", str(docs), "--settings", str(_settings_file(tmp_path))],
        pipeline_factory=lambda settings: pipeline,
    )

    assert exit_code == 0
    assert [call["path"] for call in pipeline.calls] == [first, second]
    output = capsys.readouterr().out
    assert "INGESTED document=doc-1" in output
    assert "SKIPPED document=-" in output
    assert "Summary: ingested=1 skipped=1 total=2" in output


def test_ingest_cli_returns_error_for_missing_path(tmp_path, capsys) -> None:
    exit_code = ingest.main(
        ["--path", str(tmp_path / "missing.md"), "--settings", str(_settings_file(tmp_path))],
        pipeline_factory=lambda settings: FakePipeline(),
    )

    assert exit_code == 1
    assert "Ingestion failed: ingestion path does not exist" in capsys.readouterr().err


def test_resolve_paths_rejects_unsupported_file(tmp_path) -> None:
    source = tmp_path / "sample.bin"
    source.write_bytes(b"bad")

    try:
        ingest._resolve_paths(source)
    except ValueError as exc:
        assert "unsupported file type" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected unsupported file type error")
