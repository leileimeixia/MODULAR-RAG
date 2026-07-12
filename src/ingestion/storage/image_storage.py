"""File-system image storage with a SQLite image index."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_IMAGE_ROOT = Path("data/images")
DEFAULT_DB_PATH = Path("data/db/image_index.db")


class ImageStorageError(ValueError):
    """Raised when image storage inputs or lookups are invalid."""


class ImageStorage:
    """Store image files by collection and persist image_id to path mappings."""

    def __init__(
        self,
        image_root: str | Path = DEFAULT_IMAGE_ROOT,
        db_path: str | Path = DEFAULT_DB_PATH,
    ) -> None:
        self.image_root = Path(image_root)
        self.db_path = Path(db_path)
        self.image_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_image(
        self,
        image_id: str,
        source: bytes | str | Path,
        collection: str = "default",
        doc_hash: str | None = None,
        page_num: int | None = None,
        extension: str | None = None,
        trace: Any | None = None,
    ) -> str:
        """Save an image and return the persisted file path."""
        image_id = _validate_identifier(image_id, "image_id")
        collection = _validate_identifier(collection, "collection")
        if page_num is not None and page_num < 0:
            raise ImageStorageError("page_num must be greater than or equal to 0")

        suffix = _resolve_extension(source, extension)
        target_dir = self.image_root / collection
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{image_id}{suffix}"
        _write_image(source, target_path)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO image_index (
                    image_id, file_path, collection, doc_hash, page_num
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_id) DO UPDATE SET
                    file_path = excluded.file_path,
                    collection = excluded.collection,
                    doc_hash = excluded.doc_hash,
                    page_num = excluded.page_num,
                    created_at = CURRENT_TIMESTAMP
                """,
                (image_id, str(target_path), collection, doc_hash, page_num),
            )

        if trace is not None:
            trace.record_stage(
                "image_storage",
                method="sqlite",
                details={
                    "image_id": image_id,
                    "collection": collection,
                    "file_path": str(target_path),
                },
            )
        return str(target_path)

    def get_path(self, image_id: str) -> str:
        """Return the saved path for one image id."""
        image_id = _validate_identifier(image_id, "image_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT file_path FROM image_index WHERE image_id = ?",
                (image_id,),
            ).fetchone()
        if row is None:
            raise ImageStorageError(f"image_id not found: {image_id}")
        return str(row["file_path"])

    def list_images(
        self,
        collection: str | None = None,
        doc_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        """List image index rows, optionally filtered by collection and doc hash."""
        clauses: list[str] = []
        params: list[str] = []
        if collection is not None:
            clauses.append("collection = ?")
            params.append(_validate_identifier(collection, "collection"))
        if doc_hash is not None:
            clauses.append("doc_hash = ?")
            params.append(doc_hash)

        where_sql = "" if not clauses else "WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT image_id, file_path, collection, doc_hash, page_num, created_at
                FROM image_index
                {where_sql}
                ORDER BY image_id
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_images(
        self,
        collection: str | None = None,
        doc_hash: str | None = None,
    ) -> int:
        """Delete indexed images and files matching the optional filters."""
        rows = self.list_images(collection=collection, doc_hash=doc_hash)
        for row in rows:
            Path(row["file_path"]).unlink(missing_ok=True)

        clauses: list[str] = []
        params: list[str] = []
        if collection is not None:
            clauses.append("collection = ?")
            params.append(collection)
        if doc_hash is not None:
            clauses.append("doc_hash = ?")
            params.append(doc_hash)
        where_sql = "" if not clauses else "WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            cursor = connection.execute(f"DELETE FROM image_index {where_sql}", params)
        return int(cursor.rowcount)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS image_index (
                    image_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    collection TEXT,
                    doc_hash TEXT,
                    page_num INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_collection
                ON image_index(collection)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_doc_hash
                ON image_index(doc_hash)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection


def _write_image(source: bytes | str | Path, target_path: Path) -> None:
    if isinstance(source, bytes):
        if not source:
            raise ImageStorageError("image bytes must not be empty")
        target_path.write_bytes(source)
        return

    source_path = Path(source)
    if not source_path.is_file():
        raise ImageStorageError(f"image file does not exist: {source_path}")
    shutil.copyfile(source_path, target_path)


def _resolve_extension(source: bytes | str | Path, extension: str | None) -> str:
    suffix = extension
    if suffix is None and not isinstance(source, bytes):
        suffix = Path(source).suffix
    suffix = suffix or ".png"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    if "/" in suffix or "\\" in suffix or suffix == ".":
        raise ImageStorageError("extension must be a file suffix")
    return suffix.lower()


def _validate_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImageStorageError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if "/" in normalized or "\\" in normalized:
        raise ImageStorageError(f"{field_name} must not contain path separators")
    return normalized
