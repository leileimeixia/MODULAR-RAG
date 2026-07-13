"""MVP ingestion pipeline orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import Document
from core.trace import TraceContext
from libs.loader import PdfLoader, SQLiteIntegrityChecker

from .chunking import DocumentChunker
from .embedding import BatchProcessor
from .storage import BM25Indexer, ImageStorage, VectorUpserter
from .transform import BaseTransform


LOGGER = logging.getLogger(__name__)


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
        self.logger = logger or LOGGER

    def run(
        self,
        path: str | Path,
        collection: str = "default",
        force: bool = False,
        trace: TraceContext | None = None,
    ) -> IngestionResult:
        """Run the full ingestion pipeline for one source file."""
        source_path = Path(path)
        trace = trace or TraceContext()
        file_hash = self._stage(
            "integrity",
            lambda: self.integrity_checker.compute_sha256(source_path),
            trace,
        )

        if not force and self.integrity_checker.should_skip(file_hash):
            self.logger.info("Skipping unchanged source: %s", source_path)
            trace.record_stage(
                "ingestion_skip",
                method="integrity",
                details={"file_hash": file_hash, "source_path": str(source_path)},
            )
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
            document = self._stage("load", lambda: self.loader.load(source_path), trace)
            images_saved = self._stage(
                "image_store",
                lambda: self._store_document_images(document, collection, file_hash, trace),
                trace,
            )
            chunks = self._stage("split", lambda: self.chunker.split_document(document), trace)
            for transform in self.transforms:
                chunks = self._stage(
                    f"transform:{transform.__class__.__name__}",
                    lambda transform=transform, chunks=chunks: transform.transform(chunks, trace=trace),
                    trace,
                )
            records = self._stage(
                "encode",
                lambda: self.batch_processor.process(chunks, trace=trace),
                trace,
            )
            vector_ids = self._stage(
                "vector_upsert",
                lambda: self.vector_upserter.upsert(records, trace=trace),
                trace,
            )
            self._stage("bm25_index", lambda: self.bm25_indexer.add(records, trace=trace), trace)
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
            self.integrity_checker.mark_failed(file_hash, str(exc), source_path)
            if isinstance(exc, IngestionPipelineError):
                raise
            raise IngestionPipelineError(f"pipeline failed: {exc}") from exc

    def _stage(self, name: str, action, trace: TraceContext):
        self.logger.info("Starting ingestion stage: %s", name)
        try:
            result = action()
        except Exception as exc:
            self.logger.error("Ingestion stage failed: %s", name)
            raise IngestionPipelineError(f"pipeline failed during {name}: {exc}") from exc
        self.logger.info("Finished ingestion stage: %s", name)
        return result

    def _store_document_images(
        self,
        document: Document,
        collection: str,
        file_hash: str,
        trace: TraceContext,
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
                    trace=trace,
                )
                count += 1
        return count


def _require_settings(settings: Any | None, factory):
    if settings is None:
        raise IngestionPipelineError(
            f"{factory.__name__} requires settings when no explicit component is injected"
        )
    return factory(settings)
