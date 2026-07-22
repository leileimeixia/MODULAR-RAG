"""Tests for file integrity checks."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from libs.loader.file_integrity import (
    FileIntegrityError,
    SQLiteIntegrityChecker,
    compute_sha256,
)


def test_compute_sha256_is_stable(tmp_path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("hello rag\n", encoding="utf-8")

    first_hash = compute_sha256(source)
    second_hash = compute_sha256(source)

    assert first_hash == second_hash
    assert len(first_hash) == 64


def test_compute_sha256_rejects_missing_file(tmp_path) -> None:
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileIntegrityError, match="file does not exist"):
        compute_sha256(missing)


def test_mark_success_makes_hash_skippable(tmp_path) -> None:
    db_path = tmp_path / "data" / "db" / "ingestion_history.db"
    source = tmp_path / "doc.md"
    source.write_text("# Title\n", encoding="utf-8")
    checker = SQLiteIntegrityChecker(db_path)
    file_hash = checker.compute_sha256(source)

    assert checker.should_skip(file_hash) is False

    checker.mark_success(file_hash, source, metadata={"collection": "default"})

    assert checker.should_skip(file_hash) is True
    record = checker.get_record(file_hash)
    assert record is not None
    assert record["status"] == "success"
    assert record["file_path"] == str(source)
    assert record["metadata"] == {"collection": "default"}


def test_list_processed_and_remove_record(tmp_path) -> None:
    db_path = tmp_path / "ingestion_history.db"
    checker = SQLiteIntegrityChecker(db_path)
    checker.mark_success("hash-a", "a.pdf", metadata={"collection": "docs"})
    checker.mark_failed("hash-b", "failed", file_path="b.pdf")

    success_records = checker.list_processed(collection="docs")

    assert [record["file_hash"] for record in success_records] == ["hash-a"]
    assert checker.remove_record("hash-a") == 1
    assert checker.get_record("hash-a") is None


def test_mark_failed_does_not_skip_and_success_can_overwrite(tmp_path) -> None:
    db_path = tmp_path / "ingestion_history.db"
    checker = SQLiteIntegrityChecker(db_path)
    file_hash = "abc123"

    checker.mark_failed(file_hash, "loader failed")

    assert checker.should_skip(file_hash) is False
    failed_record = checker.get_record(file_hash)
    assert failed_record is not None
    assert failed_record["status"] == "failed"
    assert failed_record["error_msg"] == "loader failed"

    checker.mark_success(file_hash, "doc.pdf")

    assert checker.should_skip(file_hash) is True
    success_record = checker.get_record(file_hash)
    assert success_record is not None
    assert success_record["status"] == "success"
    assert success_record["error_msg"] is None


def test_sqlite_database_is_created_with_wal_mode(tmp_path) -> None:
    db_path = tmp_path / "data" / "db" / "ingestion_history.db"

    SQLiteIntegrityChecker(db_path)

    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    assert journal_mode == "wal"
    assert ("file_integrity",) in tables


def test_concurrent_success_writes_are_supported(tmp_path) -> None:
    db_path = tmp_path / "ingestion_history.db"
    checker = SQLiteIntegrityChecker(db_path)

    def mark(index: int) -> bool:
        file_hash = f"hash-{index}"
        checker.mark_success(file_hash, f"doc-{index}.txt")
        return checker.should_skip(file_hash)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(mark, range(12)))

    assert all(results)
