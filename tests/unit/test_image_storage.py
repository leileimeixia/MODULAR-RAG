"""Tests for image file storage and SQLite indexing."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.trace import TraceContext
from ingestion.storage import ImageStorage, ImageStorageError


def _storage(tmp_path) -> ImageStorage:
    return ImageStorage(
        image_root=tmp_path / "images",
        db_path=tmp_path / "db" / "image_index.db",
    )


def test_save_image_bytes_persists_file_and_index(tmp_path) -> None:
    storage = _storage(tmp_path)

    path = storage.save_image(
        "img-1",
        b"fake-png",
        collection="docs",
        doc_hash="doc-hash",
        page_num=2,
    )

    assert path == str(tmp_path / "images" / "docs" / "img-1.png")
    assert (tmp_path / "images" / "docs" / "img-1.png").read_bytes() == b"fake-png"
    assert storage.get_path("img-1") == path
    rows = storage.list_images(collection="docs")
    assert rows == [
        {
            "image_id": "img-1",
            "file_path": path,
            "collection": "docs",
            "doc_hash": "doc-hash",
            "page_num": 2,
            "created_at": rows[0]["created_at"],
        }
    ]


def test_save_image_file_uses_source_suffix(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"jpg-bytes")
    storage = _storage(tmp_path)

    path = storage.save_image("img-2", source, collection="docs")

    assert path == str(tmp_path / "images" / "docs" / "img-2.jpg")
    assert (tmp_path / "images" / "docs" / "img-2.jpg").read_bytes() == b"jpg-bytes"


def test_save_image_can_replace_existing_mapping(tmp_path) -> None:
    storage = _storage(tmp_path)

    first = storage.save_image("img-1", b"old", collection="docs")
    second = storage.save_image("img-1", b"new", collection="other", extension=".webp")

    assert first != second
    assert storage.get_path("img-1") == second
    assert (tmp_path / "images" / "other" / "img-1.webp").read_bytes() == b"new"
    assert storage.list_images(collection="docs") == []


def test_list_images_filters_by_collection_and_doc_hash(tmp_path) -> None:
    storage = _storage(tmp_path)
    storage.save_image("img-a", b"a", collection="docs", doc_hash="doc-1")
    storage.save_image("img-b", b"b", collection="docs", doc_hash="doc-2")
    storage.save_image("img-c", b"c", collection="other", doc_hash="doc-1")

    assert [row["image_id"] for row in storage.list_images(collection="docs")] == [
        "img-a",
        "img-b",
    ]
    assert [row["image_id"] for row in storage.list_images(doc_hash="doc-1")] == [
        "img-a",
        "img-c",
    ]
    assert [
        row["image_id"]
        for row in storage.list_images(collection="docs", doc_hash="doc-1")
    ] == ["img-a"]


def test_sqlite_database_is_created_with_wal_mode_and_indexes(tmp_path) -> None:
    storage = _storage(tmp_path)

    assert storage.db_path.exists()
    with sqlite3.connect(storage.db_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert journal_mode == "wal"
    assert {"idx_collection", "idx_doc_hash"}.issubset(indexes)


def test_delete_images_removes_files_and_index_rows(tmp_path) -> None:
    storage = _storage(tmp_path)
    storage.save_image("img-a", b"a", collection="docs", doc_hash="doc-1")
    storage.save_image("img-b", b"b", collection="docs", doc_hash="doc-2")

    deleted = storage.delete_images(collection="docs", doc_hash="doc-1")

    assert deleted == 1
    assert [row["image_id"] for row in storage.list_images(collection="docs")] == ["img-b"]
    assert not (tmp_path / "images" / "docs" / "img-a.png").exists()


def test_missing_image_lookup_raises(tmp_path) -> None:
    with pytest.raises(ImageStorageError, match="not found"):
        _storage(tmp_path).get_path("missing")


def test_invalid_inputs_are_rejected(tmp_path) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(ImageStorageError, match="image bytes"):
        storage.save_image("img-1", b"", collection="docs")
    with pytest.raises(ImageStorageError, match="path separators"):
        storage.save_image("../bad", b"bytes", collection="docs")
    with pytest.raises(ImageStorageError, match="image file does not exist"):
        storage.save_image("img-2", tmp_path / "missing.png", collection="docs")


def test_concurrent_writes_are_supported(tmp_path) -> None:
    storage = _storage(tmp_path)

    def save(index: int) -> str:
        return storage.save_image(f"img-{index}", f"image-{index}".encode(), collection="docs")

    with ThreadPoolExecutor(max_workers=4) as executor:
        paths = list(executor.map(save, range(10)))

    assert len(paths) == 10
    assert len(storage.list_images(collection="docs")) == 10


def test_image_storage_records_trace_stage(tmp_path) -> None:
    trace = TraceContext(trace_id="trace-image")

    path = _storage(tmp_path).save_image("img-1", b"bytes", collection="docs", trace=trace)

    assert trace.stages[-1].name == "image_storage"
    assert trace.stages[-1].method == "sqlite"
    assert trace.stages[-1].details == {
        "image_id": "img-1",
        "collection": "docs",
        "file_path": path,
    }
