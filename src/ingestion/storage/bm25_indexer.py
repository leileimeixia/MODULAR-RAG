"""Persistent BM25 inverted index for sparse chunk records."""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from pathlib import Path
from typing import Any

from core import ChunkRecord


class BM25IndexerError(ValueError):
    """Raised when BM25 index construction or querying fails."""


class BM25Indexer:
    """Build, persist, load, and query a BM25 inverted index."""

    INDEX_FILENAME = "bm25_index.pkl"

    def __init__(
        self,
        index_dir: str | Path = "data/db/bm25",
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0:
            raise BM25IndexerError("k1 must be greater than 0")
        if not 0 <= b <= 1:
            raise BM25IndexerError("b must be between 0 and 1")
        self.index_dir = Path(index_dir)
        self.k1 = float(k1)
        self.b = float(b)
        self.index: dict[str, dict[str, Any]] = {}
        self.records: dict[str, dict[str, Any]] = {}
        self.doc_count = 0
        self.avg_doc_length = 0.0

    def build(self, records: list[ChunkRecord], trace: Any | None = None) -> None:
        """Rebuild the full index from sparse ChunkRecord payloads."""
        self.records = {}
        for record in records:
            _validate_record(record)
            self.records[record.id] = _record_payload(record)
        self._rebuild_index()
        self.save()
        self._record_trace("bm25_build", len(records), trace)

    def add(self, records: list[ChunkRecord], trace: Any | None = None) -> None:
        """Incrementally add or replace records, then persist the rebuilt index."""
        for record in records:
            _validate_record(record)
            self.records[record.id] = _record_payload(record)
        self._rebuild_index()
        self.save()
        self._record_trace("bm25_add", len(records), trace)

    def load(self) -> BM25Indexer:
        """Load a previously saved index into this instance."""
        index_path = self._index_path()
        if not index_path.is_file():
            raise BM25IndexerError(f"BM25 index file does not exist: {index_path}")
        with index_path.open("rb") as file:
            payload = pickle.load(file)

        self.k1 = float(payload["k1"])
        self.b = float(payload["b"])
        self.index = dict(payload["index"])
        self.records = dict(payload["records"])
        self.doc_count = int(payload["doc_count"])
        self.avg_doc_length = float(payload["avg_doc_length"])
        return self

    def save(self) -> Path:
        """Persist the current index to disk."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        index_path = self._index_path()
        with index_path.open("wb") as file:
            pickle.dump(
                {
                    "k1": self.k1,
                    "b": self.b,
                    "index": self.index,
                    "records": self.records,
                    "doc_count": self.doc_count,
                    "avg_doc_length": self.avg_doc_length,
                },
                file,
            )
        return index_path

    def query(self, query: str, top_k: int = 5) -> list[dict[str, float | str]]:
        """Return top chunk ids for a keyword query using BM25 scoring."""
        if top_k <= 0:
            raise BM25IndexerError("top_k must be greater than 0")
        if not query.strip() or not self.index:
            return []

        scores: dict[str, float] = {}
        for term, query_tf in Counter(_tokenize(query)).items():
            entry = self.index.get(term)
            if entry is None:
                continue
            for posting in entry["postings"]:
                chunk_id = str(posting["chunk_id"])
                scores[chunk_id] = scores.get(chunk_id, 0.0) + query_tf * self._score_posting(
                    float(entry["idf"]),
                    float(posting["tf"]),
                    float(posting["doc_length"]),
                )

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [
            {"chunk_id": chunk_id, "score": score}
            for chunk_id, score in ranked[:top_k]
        ]

    def _rebuild_index(self) -> None:
        self.doc_count = len(self.records)
        doc_lengths = {
            chunk_id: int(sum(payload["sparse_vector"].values()))
            for chunk_id, payload in self.records.items()
        }
        self.avg_doc_length = (
            sum(doc_lengths.values()) / self.doc_count if self.doc_count else 0.0
        )

        postings_by_term: dict[str, list[dict[str, float | str]]] = {}
        for chunk_id, payload in self.records.items():
            doc_length = doc_lengths[chunk_id]
            for term, tf in payload["sparse_vector"].items():
                postings_by_term.setdefault(term, []).append(
                    {
                        "chunk_id": chunk_id,
                        "tf": float(tf),
                        "doc_length": float(doc_length),
                    }
                )

        self.index = {}
        for term, postings in sorted(postings_by_term.items()):
            df = len(postings)
            self.index[term] = {
                "idf": _idf(self.doc_count, df),
                "postings": sorted(postings, key=lambda posting: str(posting["chunk_id"])),
            }

    def _score_posting(self, idf: float, tf: float, doc_length: float) -> float:
        if tf <= 0:
            return 0.0
        avg_doc_length = self.avg_doc_length or 1.0
        denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / avg_doc_length)
        return idf * (tf * (self.k1 + 1)) / denominator

    def _record_trace(self, stage_name: str, record_count: int, trace: Any | None) -> None:
        if trace is not None:
            trace.record_stage(
                stage_name,
                method="pickle",
                details={
                    "record_count": record_count,
                    "doc_count": self.doc_count,
                    "term_count": len(self.index),
                    "index_path": str(self._index_path()),
                },
            )

    def _index_path(self) -> Path:
        return self.index_dir / self.INDEX_FILENAME


def _validate_record(record: ChunkRecord) -> None:
    if not isinstance(record, ChunkRecord):
        raise BM25IndexerError("BM25Indexer expects ChunkRecord objects")
    if record.sparse_vector is None:
        raise BM25IndexerError(f"ChunkRecord {record.id} does not include sparse_vector")


def _record_payload(record: ChunkRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "text": record.text,
        "metadata": dict(record.metadata),
        "sparse_vector": {term: float(tf) for term, tf in (record.sparse_vector or {}).items()},
    }


def _idf(document_count: int, document_frequency: int) -> float:
    return math.log((document_count - document_frequency + 0.5) / (document_frequency + 0.5))


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in re.finditer(r"\w+", text)]
