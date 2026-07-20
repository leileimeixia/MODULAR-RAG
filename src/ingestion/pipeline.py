"""MVP ingestion pipeline orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core import Document
from core.trace import TraceCollector, TraceContext
from libs.loader import PdfLoader, SQLiteIntegrityChecker

from .chunking import DocumentChunker
from .embedding import BatchProcessor
from .storage import BM25Indexer, ImageStorage, VectorUpserter
from .transform import BaseTransform


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[str, int, int], None]


class IngestionPipelineError(RuntimeError):
    """Raised when one pipeline stage fails."""


@dataclass(frozen=True)
class IngestionResult:
    """Summary returned after one ingestion run."""

    file_hash: str
    document_id: str | None
    skipped: bool
    chunk_count: int
    record_count: int
    vector_ids: list[str]
    image_count: int
    trace: TraceContext


class IngestionPipeline:
    """Serially run integrity, load, split, transform, encode, and store stages."""

    def __init__(
        self,
        settings: Any | None = None,
        integrity_checker: Any | None = None,
        loader: Any | None = None,
        chunker: Any | None = None,
        transforms: list[BaseTransform] | None = None,
        batch_processor: Any | None = None,
        vector_upserter: Any | None = None,
        bm25_indexer: Any | None = None,
        image_storage: Any | None = None,
        trace_collector: TraceCollector | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.integrity_checker = integrity_checker or SQLiteIntegrityChecker()
        self.loader = loader or PdfLoader()
        self.chunker = chunker or _require_settings(settings, DocumentChunker)
        self.transforms = transforms or []
        self.batch_processor = batch_processor or BatchProcessor(settings=settings)
        self.vector_upserter = vector_upserter or VectorUpserter(settings=settings)
        self.bm25_indexer = bm25_indexer or BM25Indexer()
        self.image_storage = image_storage or ImageStorage()
        self.trace_collector = trace_collector or _trace_collector(settings)
        self.logger = logger or LOGGER

    def run(
        self,
        path: str | Path,
        collection: str = "default",
        force: bool = False,
        trace: TraceContext | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> IngestionResult:
        """Run the full ingestion pipeline for one source file."""
        source_path = Path(path)
        trace = trace or TraceContext(trace_type="ingestion")
        total_steps = _total_steps(len(self.transforms))
        current_step = 0
        file_hash = self._stage(
            "integrity",
            lambda: self.integrity_checker.compute_sha256(source_path),
            trace,
            method=self.integrity_checker.__class__.__name__,
            details={"source_path": str(source_path)},
        )
        current_step = _notify_progress(on_progress, "integrity", current_step, total_steps)

        if not force and self.integrity_checker.should_skip(file_hash):
            self.logger.info("Skipping unchanged source: %s", source_path)
            trace.record_stage(
                "ingestion_skip",
                method="integrity",
                details={"file_hash": file_hash, "source_path": str(source_path)},
            )
            self.trace_collector.collect(trace)
            _notify_progress(on_progress, "ingestion_skip", current_step, total_steps)
            return IngestionResult(
                file_hash=file_hash,
                document_id=None,
                skipped=True,
                chunk_count=0,
                record_count=0,
                vector_ids=[],
                image_count=0,
                trace=trace,
            )

        try:
            document = self._stage(
                "load",
                lambda: self.loader.load(source_path),
                trace,
                method=self.loader.__class__.__name__,
                details={"source_path": str(source_path)},
            )
            current_step = _notify_progress(on_progress, "load", current_step, total_steps)
            images_saved = self._stage(
                "image_store",
                lambda: self._store_document_images(document, collection, file_hash),
                trace,
                method=self.image_storage.__class__.__name__,
                details={"collection": collection, "document_id": document.id},
            )
            current_step = _notify_progress(on_progress, "image_store", current_step, total_steps)
            chunks = self._stage(
                "split",
                lambda: self.chunker.split_document(document),
                trace,
                method=self.chunker.__class__.__name__,
                details={"document_id": document.id},
            )
            current_step = _notify_progress(on_progress, "split", current_step, total_steps)
            for transform in self.transforms:
                chunks = self._stage(
                    "transform",
                    lambda transform=transform, chunks=chunks: transform.transform(chunks, trace=None),
                    trace,
                    method=transform.__class__.__name__,
                    details={"document_id": document.id},
                )
                current_step = _notify_progress(
                    on_progress,
                    "transform",
                    current_step,
                    total_steps,
                )
            records = self._stage(
                "embed",
                lambda: self.batch_processor.process(chunks, trace=None),
                trace,
                method=self.batch_processor.__class__.__name__,
                details={"document_id": document.id, "chunk_count": len(chunks)},
            )
            current_step = _notify_progress(on_progress, "embed", current_step, total_steps)
            vector_ids = self._stage(
                "upsert",
                lambda: self.vector_upserter.upsert(records, trace=None),
                trace,
                method=self.vector_upserter.__class__.__name__,
                details={"document_id": document.id, "record_count": len(records)},
            )
            current_step = _notify_progress(on_progress, "upsert", current_step, total_steps)
            self._stage(
                "bm25_index",
                lambda: self.bm25_indexer.add(records, trace=None),
                trace,
                method=self.bm25_indexer.__class__.__name__,
                details={"document_id": document.id, "record_count": len(records)},
            )
            current_step = _notify_progress(on_progress, "bm25_index", current_step, total_steps)
            self.integrity_checker.mark_success(
                file_hash,
                source_path,
                metadata={
                    "collection": collection,
                    "document_id": document.id,
                    "chunk_count": len(chunks),
                    "record_count": len(records),
                    "image_count": images_saved,
                },
            )
            trace.record_stage(
                "ingestion_complete",
                method="pipeline",
                details={
                    "file_hash": file_hash,
                    "document_id": document.id,
                    "chunk_count": len(chunks),
                    "record_count": len(records),
                    "image_count": images_saved,
                },
            )
            self.trace_collector.collect(trace)
            _notify_progress(on_progress, "ingestion_complete", current_step, total_steps)
            return IngestionResult(
                file_hash=file_hash,
                document_id=document.id,
                skipped=False,
                chunk_count=len(chunks),
                record_count=len(records),
                vector_ids=vector_ids,
                image_count=images_saved,
                trace=trace,
            )
        except Exception as exc:
            trace.record_stage(
                "ingestion_failed",
                method="pipeline",
                details={
                    "file_hash": file_hash,
                    "source_path": str(source_path),
                    "error": exc.__class__.__name__,
                },
            )
            self.trace_collector.collect(trace)
            _notify_progress(on_progress, "ingestion_failed", current_step, total_steps)
            self.integrity_checker.mark_failed(file_hash, str(exc), source_path)
            if isinstance(exc, IngestionPipelineError):
                raise
            raise IngestionPipelineError(f"pipeline failed: {exc}") from exc

    def _stage(
        self,
        name: str,
        action,
        trace: TraceContext,
        method: str,
        details: dict[str, Any] | None = None,
    ):
        self.logger.info("Starting ingestion stage: %s", name)
        started_at = time.perf_counter()
        try:
            result = action()
        except Exception as exc:
            self.logger.error("Ingestion stage failed: %s", name)
            trace.record_stage(
                name,
                method=method,
                details={
                    **(details or {}),
                    "failed": True,
                    "error": exc.__class__.__name__,
                },
                elapsed_ms=(time.perf_counter() - started_at) * 1000,
            )
            raise IngestionPipelineError(f"pipeline failed during {name}: {exc}") from exc
        trace.record_stage(
            name,
            method=method,
            details={**(details or {}), **_result_details(result), "failed": False},
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
        )
        self.logger.info("Finished ingestion stage: %s", name)
        return result

    def _store_document_images(
        self,
        document: Document,
        collection: str,
        file_hash: str,
    ) -> int:
        count = 0
        for image in document.images():
            image_path = Path(image.path)
            if image_path.is_file():
                self.image_storage.save_image(
                    image.id,
                    image_path,
                    collection=collection,
                    doc_hash=file_hash,
                    page_num=image.page,
                    trace=None,
                )
                count += 1
        return count


def _require_settings(settings: Any | None, factory):
    if settings is None:
        raise IngestionPipelineError(
            f"{factory.__name__} requires settings when no explicit component is injected"
        )
    return factory(settings)


def _trace_collector(settings: Any | None) -> TraceCollector:
    observability = getattr(settings, "observability", None)
    trace_enabled = bool(getattr(observability, "trace_enabled", False))
    trace_file = getattr(observability, "trace_file", None)
    return TraceCollector(trace_file=trace_file, persist=trace_enabled)


def _result_details(result: Any) -> dict[str, Any]:
    if isinstance(result, list):
        return {"item_count": len(result)}
    if isinstance(result, int):
        return {"count": result}
    if isinstance(result, Document):
        return {"document_id": result.id, "text_length": len(result.text)}
    return {}


def _total_steps(transform_count: int) -> int:
    return 7 + transform_count


def _notify_progress(
    on_progress: ProgressCallback | None,
    stage_name: str,
    current: int,
    total: int,
) -> int:
    next_current = min(current + 1, total)
    if on_progress is not None:
        on_progress(stage_name, next_current, total)
    return next_current
