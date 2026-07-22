"""Dashboard ingestion management service."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from core.settings import load_settings
from ingestion import DocumentManager, IngestionPipeline
from ingestion.storage import BM25Indexer, ImageStorage
from libs.loader import SQLiteIntegrityChecker
from libs.vector_store import ChromaStore
from observability.dashboard.services.data_service import DataService


SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}
ProgressSink = Callable[[str, int, int], None]


class IngestionServiceError(ValueError):
    """Raised when dashboard ingestion inputs are invalid."""


class IngestionService:
    """Save uploaded files, run ingestion, and coordinate document deletion."""

    def __init__(
        self,
        settings_path: str | Path = "config/settings.yaml",
        documents_root: str | Path = "data/documents",
        pipeline: IngestionPipeline | None = None,
        document_manager: DocumentManager | None = None,
    ) -> None:
        self.settings_path = Path(settings_path)
        self.documents_root = Path(documents_root)
        self._pipeline = pipeline
        self._document_manager = document_manager

    @property
    def pipeline(self) -> IngestionPipeline:
        """Return a lazily-created ingestion pipeline."""
        if self._pipeline is None:
            self._pipeline = IngestionPipeline(settings=load_settings(self.settings_path))
        return self._pipeline

    @property
    def document_manager(self) -> DocumentManager:
        """Return a lazily-created document manager."""
        if self._document_manager is None:
            settings = load_settings(self.settings_path)
            self._document_manager = DocumentManager(
                ChromaStore(settings.vector_store),
                BM25Indexer(),
                ImageStorage(),
                SQLiteIntegrityChecker(),
            )
        return self._document_manager

    def list_documents(self, collection: str | None = None) -> list[dict[str, Any]]:
        """Return documents available for deletion controls."""
        return DataService(document_manager=self.document_manager).list_documents(
            collection=collection
        )

    def ingest_upload(
        self,
        uploaded_file: Any,
        collection: str,
        force: bool = False,
        on_progress: ProgressSink | None = None,
    ) -> dict[str, Any]:
        """Persist an uploaded file and run the ingestion pipeline."""
        collection = _safe_segment(collection, "collection")
        file_name = _uploaded_name(uploaded_file)
        suffix = Path(file_name).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise IngestionServiceError(f"unsupported upload file type: {suffix or '<none>'}")

        target_path = self._save_upload(uploaded_file, collection, file_name)
        progress_events: list[dict[str, Any]] = []

        def record_progress(stage: str, current: int, total: int) -> None:
            event = {"stage": stage, "current": current, "total": total}
            progress_events.append(event)
            if on_progress is not None:
                on_progress(stage, current, total)

        result = self.pipeline.run(
            target_path,
            collection=collection,
            force=force,
            on_progress=record_progress,
        )
        return {
            "file_path": str(target_path),
            "collection": collection,
            "file_hash": result.file_hash,
            "document_id": result.document_id,
            "skipped": result.skipped,
            "chunk_count": result.chunk_count,
            "record_count": result.record_count,
            "image_count": result.image_count,
            "vector_ids": list(result.vector_ids),
            "progress_events": progress_events,
        }

    def delete_document(
        self,
        source_path: str,
        collection: str | None = None,
    ) -> dict[str, Any]:
        """Delete a document and return a plain dictionary for UI rendering."""
        return asdict(
            self.document_manager.delete_document(
                source_path,
                collection=collection or None,
            )
        )

    def _save_upload(self, uploaded_file: Any, collection: str, file_name: str) -> Path:
        target_dir = self.documents_root / collection
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / Path(file_name).name
        target_path.write_bytes(_uploaded_bytes(uploaded_file))
        return target_path


def _uploaded_name(uploaded_file: Any) -> str:
    name = getattr(uploaded_file, "name", "")
    if not isinstance(name, str) or not name.strip():
        raise IngestionServiceError("uploaded file must have a non-empty name")
    safe_name = Path(name.strip()).name
    if not safe_name:
        raise IngestionServiceError("uploaded file name is invalid")
    return safe_name


def _uploaded_bytes(uploaded_file: Any) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        payload = uploaded_file.getvalue()
    elif hasattr(uploaded_file, "read"):
        payload = uploaded_file.read()
    else:
        raise IngestionServiceError("uploaded file must provide getvalue() or read()")
    if not isinstance(payload, bytes) or not payload:
        raise IngestionServiceError("uploaded file bytes must not be empty")
    return payload


def _safe_segment(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestionServiceError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if "/" in normalized or "\\" in normalized:
        raise IngestionServiceError(f"{field_name} must not contain path separators")
    return normalized
