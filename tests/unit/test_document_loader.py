"""Contract tests for the multi-format document loader."""

from __future__ import annotations

import zipfile

import pytest

from core import Document
from libs.loader import DocumentLoader, LoaderError


def test_document_loader_delegates_pdf_fixture() -> None:
    document = DocumentLoader().load("tests/fixtures/sample_documents/simple.pdf")

    assert isinstance(document, Document)
    assert "Hello PDF Loader" in document.text
    assert document.metadata["doc_type"] == "pdf"


@pytest.mark.parametrize(
    ("suffix", "doc_type"),
    [
        (".txt", "txt"),
        (".md", "md"),
    ],
)
def test_document_loader_loads_plain_text_formats(tmp_path, suffix, doc_type) -> None:
    source = tmp_path / f"sample{suffix}"
    source.write_text("\ufeff# Title\n\nBody text", encoding="utf-8")

    document = DocumentLoader().load(source)

    assert document.text == "# Title\n\nBody text"
    assert document.metadata["source_path"] == str(source)
    assert document.metadata["doc_type"] == doc_type
    assert document.metadata["file_hash"] == document.id
    assert document.metadata["images"] == []


def test_document_loader_loads_docx_text(tmp_path) -> None:
    source = tmp_path / "sample.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Hello</w:t></w:r><w:r><w:t> DOCX</w:t></w:r></w:p>
    <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>
  </w:body>
</w:document>
""",
        )

    document = DocumentLoader().load(source)

    assert document.text == "Hello DOCX\nSecond paragraph"
    assert document.metadata["doc_type"] == "docx"


def test_document_loader_rejects_unsupported_file(tmp_path) -> None:
    source = tmp_path / "sample.bin"
    source.write_bytes(b"payload")

    with pytest.raises(LoaderError, match="unsupported document type"):
        DocumentLoader().load(source)


def test_document_loader_rejects_empty_text_file(tmp_path) -> None:
    source = tmp_path / "empty.md"
    source.write_text("  ", encoding="utf-8")

    with pytest.raises(LoaderError, match="no extractable text"):
        DocumentLoader().load(source)
