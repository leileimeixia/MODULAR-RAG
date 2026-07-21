"""Local persistent vector store with a Chroma-compatible adapter surface."""

from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from core.settings import VectorStoreSettings

from .base_vector_store import BaseVectorStore, Metadata, Vector, VectorQueryResult, VectorRecord


class ChromaStoreError(ValueError):
    """Raised when the local ChromaStore adapter cannot process a request."""


class ChromaStore(BaseVectorStore):
    """Persist vectors locally and expose the project VectorStore contract."""

    def __init__(self, settings: VectorStoreSettings) -> None:
        self.settings = settings
        if not settings.collection_name:
            raise ChromaStoreError("vector_store.collection_name must not be empty")
        self.persist_directory = Path(settings.persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_file = self.persist_directory / f"{settings.collection_name}.json"
        self._records = self._load_records()

    def upsert(
        self,
        records: list[VectorRecord],
        trace: Any | None = None,
    ) -> None:
        """Insert or replace records by id and persist them to disk."""
        if not isinstance(records, list):
            raise ChromaStoreError("upsert expects a list of VectorRecord objects")
        for record in records:
            _validate_record(record)
            self._records[record.id] = record
        self._persist_records()

    def query(
        self,
        vector: Vector,
        top_k: int,
        filters: Metadata | None = None,
        trace: Any | None = None,
    ) -> list[VectorQueryResult]:
        """Return top-k records ranked by cosine similarity."""
        _validate_vector(vector, "query vector")
        if top_k <= 0:
            raise ChromaStoreError("top_k must be greater than 0")

        filters = filters or {}
        matched = [
            record
            for record in self._records.values()
            if _matches_filters(record.metadata, filters)
        ]
        ranked = sorted(
            (
                VectorQueryResult(
                    id=record.id,
                    text=record.text,
                    score=_cosine_similarity(vector, record.vector),
                    metadata=record.metadata,
                )
                for record in matched
            ),
            key=lambda result: (-result.score, result.id),
        )
        return ranked[:top_k]

    def get_all(self) -> list[VectorRecord]:
        """Return all records in deterministic id order."""
        return [self._records[key] for key in sorted(self._records)]

    def get_collection_stats(self) -> dict[str, Any]:
        """Return lightweight collection statistics for dashboard views."""
        records = self.get_all()
        sources = {
            str(source)
            for record in records
            for source in (
                record.metadata.get("source_path"),
                record.metadata.get("source"),
            )
            if source
        }
        return {
            "collection_name": self.settings.collection_name,
            "provider": self.settings.provider,
            "persist_directory": str(self.persist_directory),
            "collection_file": str(self.collection_file),
            "record_count": len(records),
            "source_count": len(sources),
        }

    def get_by_ids(
        self,
        ids: list[str],
        trace: Any | None = None,
    ) -> list[VectorRecord]:
        """Return records for existing ids in the same order they were requested."""
        if not isinstance(ids, list):
            raise ChromaStoreError("get_by_ids expects a list of ids")
        if not all(isinstance(item, str) and item for item in ids):
            raise ChromaStoreError("get_by_ids ids must be non-empty strings")
        return [
            self._records[record_id]
            for record_id in ids
            if record_id in self._records
        ]

    def get_by_metadata(self, filters: Metadata) -> list[VectorRecord]:
        """Return records whose metadata contains all filter key/value pairs."""
        return [
            record
            for record in self.get_all()
            if _matches_filters(record.metadata, filters)
        ]

    def _load_records(self) -> dict[str, VectorRecord]:
        if not self.collection_file.exists():
            return {}
        try:
            payload = json.loads(self.collection_file.read_text(encoding="utf-8"))
            raw_records = payload.get("records", [])
        except (json.JSONDecodeError, OSError) as exc:
            raise ChromaStoreError(
                f"Failed to load vector store collection: {self.collection_file}"
            ) from exc

        records: dict[str, VectorRecord] = {}
        for item in raw_records:
            record = VectorRecord(
                id=str(item["id"]),
                text=str(item["text"]),
                vector=[float(value) for value in item["vector"]],
                metadata=dict(item.get("metadata", {})),
            )
            _validate_record(record)
            records[record.id] = record
        return records

    def _persist_records(self) -> None:
        payload = {
            "collection_name": self.settings.collection_name,
            "records": [
                {
                    "id": record.id,
                    "text": record.text,
                    "vector": record.vector,
                    "metadata": record.metadata,
                }
                for record in self.get_all()
            ],
        }
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.persist_directory,
            delete=False,
        ) as temp_file:
            json.dump(payload, temp_file, ensure_ascii=False, indent=2, sort_keys=True)
            temp_path = Path(temp_file.name)
        temp_path.replace(self.collection_file)


def _validate_record(record: VectorRecord) -> None:
    if not isinstance(record, VectorRecord):
        raise ChromaStoreError("upsert records must be VectorRecord objects")
    if not record.id:
        raise ChromaStoreError("VectorRecord.id must not be empty")
    if not isinstance(record.text, str):
        raise ChromaStoreError("VectorRecord.text must be a string")
    _validate_vector(record.vector, f"VectorRecord[{record.id}].vector")


def _validate_vector(vector: Vector, label: str) -> None:
    if not isinstance(vector, list) or not vector:
        raise ChromaStoreError(f"{label} must be a non-empty list")
    if not all(isinstance(value, int | float) for value in vector):
        raise ChromaStoreError(f"{label} must contain only numeric values")


def _matches_filters(metadata: Metadata, filters: Metadata) -> bool:
    return all(metadata.get(key) == value for key, value in filters.items())


def _cosine_similarity(left: Vector, right: Vector) -> float:
    if len(left) != len(right):
        raise ChromaStoreError("query vector and record vector dimensions must match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    return dot / (left_norm * right_norm)
