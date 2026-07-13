"""Shared data contracts for ingestion, retrieval, and MCP tools."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


Metadata = dict[str, Any]
DenseVector = list[float]
SparseVector = dict[str, float]


@dataclass(frozen=True)
class ImageRef:
    """Metadata for an image placeholder embedded in document text."""

    id: str
    path: str
    text_offset: int
    text_length: int
    page: int | None = None
    position: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise CoreTypeError("ImageRef.id must not be empty")
        if not self.path:
            raise CoreTypeError("ImageRef.path must not be empty")
        if self.text_offset < 0:
            raise CoreTypeError("ImageRef.text_offset must be greater than or equal to 0")
        if self.text_length <= 0:
            raise CoreTypeError("ImageRef.text_length must be greater than 0")
        if self.page is not None and self.page < 0:
            raise CoreTypeError("ImageRef.page must be greater than or equal to 0")

    def placeholder(self) -> str:
        """Return the canonical placeholder used inside Document.text."""
        return image_placeholder(self.id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "path": self.path,
            "page": self.page,
            "text_offset": self.text_offset,
            "text_length": self.text_length,
            "position": dict(self.position),
        }

    @classmethod
    def from_dict(cls, payload: Metadata) -> ImageRef:
        """Create an ImageRef from a dictionary."""
        return cls(
            id=str(payload["id"]),
            path=str(payload["path"]),
            page=payload.get("page"),
            text_offset=int(payload["text_offset"]),
            text_length=int(payload["text_length"]),
            position=dict(payload.get("position", {})),
        )


@dataclass(frozen=True)
class Document:
    """A loaded source document before chunking."""

    id: str
    text: str
    metadata: Metadata

    def __post_init__(self) -> None:
        _validate_id(self.id, "Document.id")
        _validate_text(self.text, "Document.text")
        _validate_metadata(self.metadata, "Document.metadata")
        object.__setattr__(self, "metadata", _serialize_metadata(self.metadata))

    def images(self) -> list[ImageRef]:
        """Return normalized image references from metadata.images."""
        return _metadata_images(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "metadata": _serialize_metadata(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Metadata) -> Document:
        """Create a Document from a dictionary."""
        return cls(
            id=str(payload["id"]),
            text=str(payload["text"]),
            metadata=dict(payload["metadata"]),
        )

    def to_json(self) -> str:
        """Serialize to a stable JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> Document:
        """Create a Document from a JSON string."""
        return cls.from_dict(json.loads(payload))


@dataclass(frozen=True)
class Chunk:
    """A text chunk with offsets back into its source document."""

    id: str
    text: str
    metadata: Metadata
    start_offset: int
    end_offset: int
    source_ref: str | None = None

    def __post_init__(self) -> None:
        _validate_id(self.id, "Chunk.id")
        _validate_text(self.text, "Chunk.text")
        _validate_metadata(self.metadata, "Chunk.metadata")
        _validate_offsets(self.start_offset, self.end_offset)
        object.__setattr__(self, "metadata", _serialize_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "metadata": _serialize_metadata(self.metadata),
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "source_ref": self.source_ref,
        }

    @classmethod
    def from_dict(cls, payload: Metadata) -> Chunk:
        """Create a Chunk from a dictionary."""
        return cls(
            id=str(payload["id"]),
            text=str(payload["text"]),
            metadata=dict(payload["metadata"]),
            start_offset=int(payload["start_offset"]),
            end_offset=int(payload["end_offset"]),
            source_ref=payload.get("source_ref"),
        )


@dataclass(frozen=True)
class ChunkRecord:
    """Storage/retrieval payload for a chunk and its optional vectors."""

    id: str
    text: str
    metadata: Metadata
    dense_vector: DenseVector | None = None
    sparse_vector: SparseVector | None = None

    def __post_init__(self) -> None:
        _validate_id(self.id, "ChunkRecord.id")
        _validate_text(self.text, "ChunkRecord.text")
        _validate_metadata(self.metadata, "ChunkRecord.metadata")
        if self.dense_vector is not None:
            _validate_dense_vector(self.dense_vector, "ChunkRecord.dense_vector")
        if self.sparse_vector is not None:
            _validate_sparse_vector(self.sparse_vector, "ChunkRecord.sparse_vector")
        object.__setattr__(self, "metadata", _serialize_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "metadata": _serialize_metadata(self.metadata),
            "dense_vector": None
            if self.dense_vector is None
            else [float(value) for value in self.dense_vector],
            "sparse_vector": None
            if self.sparse_vector is None
            else {key: float(value) for key, value in self.sparse_vector.items()},
        }

    @classmethod
    def from_dict(cls, payload: Metadata) -> ChunkRecord:
        """Create a ChunkRecord from a dictionary."""
        return cls(
            id=str(payload["id"]),
            text=str(payload["text"]),
            metadata=dict(payload["metadata"]),
            dense_vector=payload.get("dense_vector"),
            sparse_vector=payload.get("sparse_vector"),
        )


@dataclass(frozen=True)
class RetrievalResult:
    """Normalized retrieval result returned by dense/sparse/hybrid search."""

    chunk_id: str
    score: float
    text: str
    metadata: Metadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id(self.chunk_id, "RetrievalResult.chunk_id")
        if not isinstance(self.score, int | float):
            raise CoreTypeError("RetrievalResult.score must be numeric")
        _validate_text(self.text, "RetrievalResult.text")
        if not isinstance(self.metadata, dict):
            raise CoreTypeError("RetrievalResult.metadata must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "score": float(self.score),
            "text": self.text,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Metadata) -> RetrievalResult:
        """Create a RetrievalResult from a dictionary."""
        return cls(
            chunk_id=str(payload["chunk_id"]),
            score=float(payload["score"]),
            text=str(payload["text"]),
            metadata=dict(payload.get("metadata", {})),
        )


class CoreTypeError(ValueError):
    """Raised when shared core data contracts are invalid."""


def image_placeholder(image_id: str) -> str:
    """Return the canonical image placeholder for Document.text."""
    if not image_id:
        raise CoreTypeError("image_id must not be empty")
    return f"[IMAGE: {image_id}]"


def _validate_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise CoreTypeError(f"{field_name} must be a non-empty string")


def _validate_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise CoreTypeError(f"{field_name} must be a string")


def _validate_metadata(metadata: Metadata, field_name: str) -> None:
    if not isinstance(metadata, dict):
        raise CoreTypeError(f"{field_name} must be a dictionary")
    source_path = metadata.get("source_path")
    if not isinstance(source_path, str) or not source_path:
        raise CoreTypeError(f"{field_name}.source_path must be a non-empty string")
    _metadata_images(metadata)


def _metadata_images(metadata: Metadata) -> list[ImageRef]:
    images = metadata.get("images", [])
    if images is None:
        return []
    if not isinstance(images, list):
        raise CoreTypeError("metadata.images must be a list")
    return [
        image if isinstance(image, ImageRef) else ImageRef.from_dict(dict(image))
        for image in images
    ]


def _serialize_metadata(metadata: Metadata) -> Metadata:
    serialized = dict(metadata)
    if "images" in serialized and serialized["images"] is not None:
        serialized["images"] = [
            image.to_dict() if isinstance(image, ImageRef) else ImageRef.from_dict(dict(image)).to_dict()
            for image in serialized["images"]
        ]
    return serialized


def _validate_offsets(start_offset: int, end_offset: int) -> None:
    if start_offset < 0:
        raise CoreTypeError("Chunk.start_offset must be greater than or equal to 0")
    if end_offset < start_offset:
        raise CoreTypeError("Chunk.end_offset must be greater than or equal to start_offset")


def _validate_dense_vector(vector: DenseVector, field_name: str) -> None:
    if not isinstance(vector, list) or not vector:
        raise CoreTypeError(f"{field_name} must be a non-empty list")
    if not all(isinstance(value, int | float) for value in vector):
        raise CoreTypeError(f"{field_name} must contain only numeric values")


def _validate_sparse_vector(vector: SparseVector, field_name: str) -> None:
    if not isinstance(vector, dict):
        raise CoreTypeError(f"{field_name} must be a dictionary")
    if not all(isinstance(key, str) for key in vector):
        raise CoreTypeError(f"{field_name} keys must be strings")
    if not all(isinstance(value, int | float) for value in vector.values()):
        raise CoreTypeError(f"{field_name} values must be numeric")
