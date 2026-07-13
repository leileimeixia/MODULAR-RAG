"""Tests for shared core data contracts."""

from __future__ import annotations

import json

import pytest

from core import Chunk, ChunkRecord, CoreTypeError, Document, ImageRef, RetrievalResult, image_placeholder


def test_document_serializes_to_stable_dict_and_json() -> None:
    image = ImageRef(
        id="doc_hash_1_0",
        path="data/images/test/doc_hash_1_0.png",
        page=1,
        text_offset=8,
        text_length=len(image_placeholder("doc_hash_1_0")),
        position={"x": 10, "y": 20},
    )
    document = Document(
        id="doc-1",
        text=f"Before {image.placeholder()} after",
        metadata={
            "source_path": "docs/sample.pdf",
            "images": [image],
        },
    )

    payload = document.to_dict()

    assert payload == {
        "id": "doc-1",
        "text": "Before [IMAGE: doc_hash_1_0] after",
        "metadata": {
            "source_path": "docs/sample.pdf",
            "images": [
                {
                    "id": "doc_hash_1_0",
                    "path": "data/images/test/doc_hash_1_0.png",
                    "page": 1,
                    "text_offset": 8,
                    "text_length": len(image_placeholder("doc_hash_1_0")),
                    "position": {"x": 10, "y": 20},
                }
            ],
        },
    }
    assert Document.from_json(document.to_json()) == document


def test_document_accepts_image_metadata_dicts() -> None:
    document = Document(
        id="doc-1",
        text="A [IMAGE: img-1] marker",
        metadata={
            "source_path": "docs/sample.md",
            "images": [
                {
                    "id": "img-1",
                    "path": "data/images/test/img-1.png",
                    "page": 0,
                    "text_offset": 2,
                    "text_length": len(image_placeholder("img-1")),
                    "position": {},
                }
            ],
        },
    )

    assert document.images() == [
        ImageRef(
            id="img-1",
            path="data/images/test/img-1.png",
            page=0,
            text_offset=2,
            text_length=14,
            position={},
        )
    ]


def test_metadata_requires_source_path() -> None:
    with pytest.raises(CoreTypeError, match="source_path"):
        Document(id="doc-1", text="text", metadata={})


def test_chunk_validates_offsets_and_serializes() -> None:
    chunk = Chunk(
        id="chunk-1",
        text="hello",
        metadata={"source_path": "docs/sample.md"},
        start_offset=10,
        end_offset=15,
        source_ref="doc-1",
    )

    assert chunk.to_dict() == {
        "id": "chunk-1",
        "text": "hello",
        "metadata": {"source_path": "docs/sample.md"},
        "start_offset": 10,
        "end_offset": 15,
        "source_ref": "doc-1",
    }
    assert Chunk.from_dict(chunk.to_dict()) == chunk


def test_chunk_rejects_invalid_offsets() -> None:
    with pytest.raises(CoreTypeError, match="end_offset"):
        Chunk(
            id="chunk-1",
            text="hello",
            metadata={"source_path": "docs/sample.md"},
            start_offset=20,
            end_offset=10,
        )


def test_chunk_record_serializes_optional_vectors() -> None:
    record = ChunkRecord(
        id="chunk-1",
        text="hello",
        metadata={"source_path": "docs/sample.md"},
        dense_vector=[1, 2.5],
        sparse_vector={"hello": 1, "world": 0.5},
    )

    assert record.to_dict() == {
        "id": "chunk-1",
        "text": "hello",
        "metadata": {"source_path": "docs/sample.md"},
        "dense_vector": [1.0, 2.5],
        "sparse_vector": {"hello": 1.0, "world": 0.5},
    }
    assert ChunkRecord.from_dict(json.loads(json.dumps(record.to_dict()))) == record


def test_chunk_record_rejects_bad_vectors() -> None:
    with pytest.raises(CoreTypeError, match="dense_vector"):
        ChunkRecord(
            id="chunk-1",
            text="hello",
            metadata={"source_path": "docs/sample.md"},
            dense_vector=["bad"],
        )

    with pytest.raises(CoreTypeError, match="sparse_vector"):
        ChunkRecord(
            id="chunk-1",
            text="hello",
            metadata={"source_path": "docs/sample.md"},
            sparse_vector={"term": "bad"},
        )


def test_retrieval_result_serializes_roundtrip() -> None:
    result = RetrievalResult(
        chunk_id="chunk-1",
        score=0.75,
        text="retrieved text",
        metadata={"source_path": "docs/sample.md", "collection": "docs"},
    )

    payload = result.to_dict()

    assert payload == {
        "chunk_id": "chunk-1",
        "score": 0.75,
        "text": "retrieved text",
        "metadata": {"source_path": "docs/sample.md", "collection": "docs"},
    }
    assert RetrievalResult.from_dict(payload) == result


def test_retrieval_result_rejects_invalid_score() -> None:
    with pytest.raises(CoreTypeError, match="score"):
        RetrievalResult(
            chunk_id="chunk-1",
            score="bad",
            text="text",
            metadata={"source_path": "docs/sample.md"},
        )
