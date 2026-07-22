"""Ingestion pipeline layer."""

from .document_manager import (
    CollectionStats,
    DeleteResult,
    DocumentDetail,
    DocumentInfo,
    DocumentManager,
    DocumentManagerError,
)
from .pipeline import IngestionPipeline, IngestionPipelineError, IngestionResult

__all__ = [
    "CollectionStats",
    "DeleteResult",
    "DocumentDetail",
    "DocumentInfo",
    "DocumentManager",
    "DocumentManagerError",
    "IngestionPipeline",
    "IngestionPipelineError",
    "IngestionResult",
]
