"""Contract tests for PDF loading."""

from __future__ import annotations

import pytest

from core import Document
from libs.loader import BaseLoader, LoaderError, PdfLoader


def test_pdf_loader_loads_text_pdf_fixture() -> None:
    loader = PdfLoader()

    document = loader.load("tests/fixtures/sample_documents/simple.pdf")

    assert isinstance(document, Document)
    assert len(document.id) == 64
    assert "Hello PDF Loader" in document.text
    assert document.metadata["source_path"].endswith("simple.pdf")
    assert document.metadata["doc_type"] == "pdf"
    assert document.metadata["file_hash"] == document.id
    assert document.metadata["images"] == []


def test_pdf_loader_rejects_missing_file(tmp_path) -> None:
    loader = PdfLoader()

    with pytest.raises(LoaderError, match="does not exist"):
        loader.load(tmp_path / "missing.pdf")


def test_pdf_loader_rejects_non_pdf(tmp_path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("not pdf", encoding="utf-8")
    loader = PdfLoader()

    with pytest.raises(LoaderError, match=".pdf"):
        loader.load(source)


def test_pdf_loader_reports_pdf_without_extractable_text(tmp_path) -> None:
    source = tmp_path / "empty.pdf"
    source.write_bytes(b"%PDF-1.4\n%%EOF\n")
    loader = PdfLoader()

    with pytest.raises(LoaderError, match="no extractable text"):
        loader.load(source)


def test_base_loader_contract_requires_load() -> None:
    with pytest.raises(TypeError):
        BaseLoader()
