"""Tests for ingestion pipeline progress callbacks."""

from __future__ import annotations

from tests.integration.test_ingestion_pipeline import FakeIntegrityChecker, _pipeline


def test_ingestion_pipeline_reports_progress_for_full_run(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    pipeline, _ = _pipeline(tmp_path)
    events: list[tuple[str, int, int]] = []

    pipeline.run(source, on_progress=lambda stage, current, total: events.append((stage, current, total)))

    assert events == [
        ("integrity", 1, 8),
        ("load", 2, 8),
        ("image_store", 3, 8),
        ("split", 4, 8),
        ("transform", 5, 8),
        ("embed", 6, 8),
        ("upsert", 7, 8),
        ("bm25_index", 8, 8),
        ("ingestion_complete", 8, 8),
    ]


def test_ingestion_pipeline_reports_skip_progress(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    pipeline, _ = _pipeline(
        tmp_path,
        integrity_checker=FakeIntegrityChecker(skip=True),
    )
    events: list[tuple[str, int, int]] = []

    pipeline.run(source, on_progress=lambda stage, current, total: events.append((stage, current, total)))

    assert events == [
        ("integrity", 1, 8),
        ("ingestion_skip", 2, 8),
    ]


def test_ingestion_pipeline_accepts_no_progress_callback(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    pipeline, _ = _pipeline(tmp_path)

    result = pipeline.run(source, on_progress=None)

    assert result.skipped is False
    assert result.trace.stages[-1].name == "ingestion_complete"
