"""Tests for document-to-chunk adaptation."""

from __future__ import annotations

import pytest

from core import Document, ImageRef, image_placeholder
from core.settings import SplitterSettings
from ingestion.chunking import DocumentChunker, DocumentChunkerError
from libs.splitter import BaseSplitter


class FakeSplitter(BaseSplitter):
    def split_text(self, text: str, trace=None) -> list[str]:
        return [part.strip() for part in text.split("|") if part.strip()]


def _document() -> Document:
    image_one = ImageRef(
        id="img-1",
        path="data/images/doc/img-1.png",
        page=0,
        text_offset=14,
        text_length=len(image_placeholder("img-1")),
    )
    image_two = ImageRef(
        id="img-2",
        path="data/images/doc/img-2.png",
        page=1,
        text_offset=54,
        text_length=len(image_placeholder("img-2")),
    )
    return Document(
        id="doc-abc",
        text=(
            f"Intro section {image_one.placeholder()} | "
            "Text only section | "
            f"Closing section {image_two.placeholder()}"
        ),
        metadata={
            "source_path": "docs/sample.pdf",
            "doc_type": "pdf",
            "title": "Sample",
            "images": [image_one, image_two],
        },
    )


def test_document_chunker_uses_injected_splitter_and_creates_chunks() -> None:
    chunker = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0),
        splitter=FakeSplitter(),
    )

    chunks = chunker.split_document(_document())

    assert [chunk.text for chunk in chunks] == [
        "Intro section [IMAGE: img-1]",
        "Text only section",
        "Closing section [IMAGE: img-2]",
    ]
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == [0, 1, 2]
    assert all(chunk.source_ref == "doc-abc" for chunk in chunks)


def test_chunk_ids_are_unique_and_deterministic() -> None:
    document = _document()
    chunker = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0),
        splitter=FakeSplitter(),
    )

    first = chunker.split_document(document)
    second = chunker.split_document(document)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert len({chunk.id for chunk in first}) == len(first)
    assert first[0].id.startswith("doc-abc_0000_")


def test_document_metadata_is_inherited_with_chunk_index() -> None:
    chunker = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0),
        splitter=FakeSplitter(),
    )

    chunk = chunker.split_document(_document())[0]

    assert chunk.metadata["source_path"] == "docs/sample.pdf"
    assert chunk.metadata["doc_type"] == "pdf"
    assert chunk.metadata["title"] == "Sample"
    assert chunk.metadata["chunk_index"] == 0


def test_image_refs_are_distributed_only_to_referencing_chunks() -> None:
    chunker = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0),
        splitter=FakeSplitter(),
    )

    chunks = chunker.split_document(_document())

    assert chunks[0].metadata["image_refs"] == ["img-1"]
    assert [image["id"] for image in chunks[0].metadata["images"]] == ["img-1"]
    assert "images" not in chunks[1].metadata
    assert "image_refs" not in chunks[1].metadata
    assert chunks[2].metadata["image_refs"] == ["img-2"]
    assert [image["id"] for image in chunks[2].metadata["images"]] == ["img-2"]


def test_chunks_include_source_offsets() -> None:
    chunker = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0),
        splitter=FakeSplitter(),
    )

    chunks = chunker.split_document(_document())

    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(chunks[0].text)
    assert _document().text[chunks[2].start_offset : chunks[2].end_offset] == chunks[2].text


def test_document_chunker_can_use_configured_recursive_splitter() -> None:
    document = Document(
        id="doc-long",
        text=" ".join(f"word{i}" for i in range(30)),
        metadata={"source_path": "docs/long.md"},
    )

    small = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=40, chunk_overlap=0)
    )
    large = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=200, chunk_overlap=0)
    )

    assert len(small.split_document(document)) > len(large.split_document(document))


def test_document_chunker_rejects_non_document() -> None:
    chunker = DocumentChunker(
        SplitterSettings(provider="recursive", chunk_size=100, chunk_overlap=0),
        splitter=FakeSplitter(),
    )

    with pytest.raises(DocumentChunkerError, match="expects a Document"):
        chunker.split_document("not a document")
