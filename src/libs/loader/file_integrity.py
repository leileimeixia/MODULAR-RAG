"""File integrity checks for incremental ingestion."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data/db/ingestion_history.db")
SUCCESS = "success"
FAILED = "failed"


class FileIntegrityError(ValueError):
    """Raised when file integrity inputs are invalid."""


class FileIntegrityChecker(ABC):
    """Contract for file integrity state used by ingestion."""

    @abstractmethod
    def compute_sha256(self, path: str | Path) -> str:
        """Return the SHA256 digest for a file."""

    @abstractmethod
    def should_skip(self, file_hash: str) -> bool:
        """Return True when a file hash has already completed successfully."""

    @abstractmethod
    def mark_success(
        self,
        file_hash: str,
        file_path: str | Path,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a successful ingestion."""

    @abstractmethod
    def mark_failed(
        self,
        file_hash: str,
        error_msg: str,
        file_path: str | Path | None = None,
    ) -> None:
        """Record a failed ingestion."""


class SQLiteIntegrityChecker(FileIntegrityChecker):
    """SQLite-backed integrity checker using WAL for concurrent writers."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def compute_sha256(self, path: str | Path) -> str:
        """Return the SHA256 digest for a file."""
        return compute_sha256(path)

    def should_skip(self, file_hash: str) -> bool:
        """Return True when the hash has a successful ingestion record."""
        _validate_hash(file_hash)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM file_integrity WHERE file_hash = ?",
                (file_hash,),
            ).fetchone()
        return row is not None and row["status"] == SUCCESS

    def mark_success(
        self,
        file_hash: str,
        file_path: str | Path,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a successful ingestion."""
        _validate_hash(file_hash)
        file_path_text = _validate_file_path(file_path)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO file_integrity (
                    file_hash, file_path, status, processed_at, error_msg, metadata
                )
                VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(file_hash) DO UPDATE SET
                    file_path = excluded.file_path,
                    status = excluded.status,
                    processed_at = excluded.processed_at,
                    error_msg = NULL,
                    metadata = excluded.metadata
                """,
                (
                    file_hash,
                    file_path_text,
                    SUCCESS,
                    _utc_now_iso(),
                    metadata_json,
                ),
            )

    def mark_failed(
        self,
        file_hash: str,
        error_msg: str,
        file_path: str | Path | None = None,
    ) -> None:
        """Record a failed ingestion."""
        _validate_hash(file_hash)
        if not error_msg:
            raise FileIntegrityError("error_msg must not be empty")
        file_path_text = None if file_path is None else _validate_file_path(file_path)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO file_integrity (
                    file_hash, file_path, status, processed_at, error_msg, metadata
                )
                VALUES (?, ?, ?, ?, ?, '{}')
                ON CONFLICT(file_hash) DO UPDATE SET
                    file_path = COALESCE(excluded.file_path, file_integrity.file_path),
                    status = excluded.status,
                    processed_at = excluded.processed_at,
                    error_msg = excluded.error_msg
                """,
                (
                    file_hash,
                    file_path_text,
                    FAILED,
                    _utc_now_iso(),
                    error_msg,
                ),
            )

    def get_record(self, file_hash: str) -> dict[str, Any] | None:
        """Return a persisted integrity record, mainly for management and tests."""
        _validate_hash(file_hash)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT file_hash, file_path, status, processed_at, error_msg, metadata
                FROM file_integrity
                WHERE file_hash = ?
                """,
                (file_hash,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["metadata"] = json.loads(record["metadata"] or "{}")
        return record

    def list_processed(
        self,
        status: str | None = SUCCESS,
        collection: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return persisted integrity records, optionally filtered for management views."""
        params: list[str] = []
        clauses: list[str] = []
        if status is not None:
            if status not in {SUCCESS, FAILED}:
                raise FileIntegrityError("status must be success, failed, or None")
            clauses.append("status = ?")
            params.append(status)

        where_sql = "" if not clauses else "WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT file_hash, file_path, status, processed_at, error_msg, metadata
                FROM file_integrity
                {where_sql}
                ORDER BY processed_at DESC, file_hash
                """,
                params,
            ).fetchall()

        records = []
        for row in rows:
            record = dict(row)
            record["metadata"] = json.loads(record["metadata"] or "{}")
            if collection is not None and record["metadata"].get("collection") != collection:
                continue
            records.append(record)
        return records

    def remove_record(self, file_hash: str) -> int:
        """Delete one integrity record by file hash."""
        _validate_hash(file_hash)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM file_integrity WHERE file_hash = ?",
                (file_hash,),
            )
        return int(cursor.rowcount)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_integrity (
                    file_hash TEXT PRIMARY KEY,
                    file_path TEXT,
                    status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
                    processed_at TEXT NOT NULL,
                    error_msg TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_file_integrity_status
                ON file_integrity(status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_file_integrity_file_path
                ON file_integrity(file_path)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection


def compute_sha256(path: str | Path) -> str:
    """Compute a stable SHA256 digest for a file path."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileIntegrityError(f"file does not exist: {file_path}")

    digest = hashlib.sha256()
    with file_path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_hash(file_hash: str) -> None:
    if not isinstance(file_hash, str) or not file_hash:
        raise FileIntegrityError("file_hash must be a non-empty string")


def _validate_file_path(file_path: str | Path) -> str:
    file_path_text = str(file_path)
    if not file_path_text:
        raise FileIntegrityError("file_path must not be empty")
    return file_path_text


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
