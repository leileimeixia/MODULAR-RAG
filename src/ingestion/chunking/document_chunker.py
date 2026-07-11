"""Business adapter from Document objects to Chunk objects."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from core import Chunk, Document, ImageRef
from core.settings import Settings, SplitterSettings
from libs.splitter import BaseSplitter, SplitterFactory


_IMAGE_PLACEHOLDER_RE = re.compile(r"\[IMAGE:\s*([^\]]+?)\s*\]")


class DocumentChunkerError(ValueError):
    """Raised when document chunking inputs are invalid."""


class DocumentChunker:
    """Convert a Document into ordered Chunk objects using a text splitter."""

    def __init__(
        self,
        settings: Settings | SplitterSettings | Any,
        splitter: BaseSplitter | None = None,
    ) -> None:
        self.splitter = splitter or SplitterFactory.create(settings)

    def split_document(self, document: Document) -> list[Chunk]:
        """Split a Document into Chunk objects with inherited business metadata."""
        if not isinstance(document, Document):
            raise DocumentChunkerError("split_document expects a Document")

        chunk_texts = self.splitter.split_text(document.text)
        chunks: list[Chunk] = []
        cursor = 0
        for index, chunk_text in enumerate(chunk_texts):
            start_offset = _find_offset(document.text, chunk_text, cursor)
            end_offset = start_offset + len(chunk_text)
            cursor = max(cursor, end_offset)
            chunks.append(
                Chunk(
                    id=self._generate_chunk_id(document.id, index, chunk_text),
                    text=chunk_text,
                    metadata=self._inherit_metadata(document, index, chunk_text),
                    start_offset=start_offset,
                    end_offset=end_offset,
                    source_ref=document.id,
                )
            )
        return chunks

    def _generate_chunk_id(self, doc_id: str, index: int, text: str) -> str:
        """Generate a deterministic chunk id for a document/index/text tuple."""
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        return f"{doc_id}_{index:04d}_{text_hash}"

    def _inherit_metadata(
        self,
        document: Document,
        chunk_index: int,
        chunk_text: str,
    ) -> dict[str, Any]:
        """Copy document metadata and distribute image refs used by this chunk."""
        metadata = deepcopy(document.metadata)
        all_images = _image_map(document.images())
        referenced_ids = _image_refs_in_text(chunk_text)

        metadata.pop("images", None)
        metadata["chunk_index"] = chunk_index
        if referenced_ids:
            images = [
                all_images[image_id].to_dict()
                for image_id in referenced_ids
                if image_id in all_images
            ]
            if images:
                metadata["images"] = images
            metadata["image_refs"] = referenced_ids
        return metadata


def _find_offset(document_text: str, chunk_text: str, cursor: int) -> int:
    start_offset = document_text.find(chunk_text, cursor)
    if start_offset >= 0:
        return start_offset
    start_offset = document_text.find(chunk_text)
    if start_offset >= 0:
        return start_offset
    return cursor


def _image_map(images: list[ImageRef]) -> dict[str, ImageRef]:
    return {image.id: image for image in images}


def _image_refs_in_text(text: str) -> list[str]:
    refs: list[str] = []
    for match in _IMAGE_PLACEHOLDER_RE.finditer(text):
        image_id = match.group(1).strip()
        if image_id and image_id not in refs:
            refs.append(image_id)
    return refs
