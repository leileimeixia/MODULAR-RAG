"""Multi-format document loader for ingestion entrypoints."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from core import Document

from .base_loader import BaseLoader, LoaderError
from .file_integrity import compute_sha256
from .pdf_loader import PdfLoader


class DocumentLoader(BaseLoader):
    """Load supported project document formats into the shared Document contract."""

    SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}

    def __init__(self, pdf_loader: PdfLoader | None = None) -> None:
        self.pdf_loader = pdf_loader or PdfLoader()

    def load(self, path: str | Path) -> Document:
        source_path = Path(path)
        if not source_path.is_file():
            raise LoaderError(f"document file does not exist: {source_path}")

        suffix = source_path.suffix.lower()
        if suffix == ".pdf":
            return self.pdf_loader.load(source_path)
        if suffix in {".txt", ".md"}:
            return _load_text_document(source_path, doc_type=suffix[1:])
        if suffix == ".docx":
            return _load_docx_document(source_path)
        raise LoaderError(f"unsupported document type: {suffix or '<none>'}")


def _load_text_document(path: Path, doc_type: str) -> Document:
    text = _normalize_text(path.read_text(encoding="utf-8-sig"))
    if not text:
        raise LoaderError(f"no extractable text found in document: {path}")
    file_hash = compute_sha256(path)
    return Document(
        id=file_hash,
        text=text,
        metadata={
            "source_path": str(path),
            "doc_type": doc_type,
            "file_hash": file_hash,
            "images": [],
        },
    )


def _load_docx_document(path: Path) -> Document:
    try:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise LoaderError(f"failed to read DOCX document text: {path}") from exc

    text = _normalize_text(_extract_docx_text(payload))
    if not text:
        raise LoaderError(f"no extractable text found in DOCX: {path}")
    file_hash = compute_sha256(path)
    return Document(
        id=file_hash,
        text=text,
        metadata={
            "source_path": str(path),
            "doc_type": "docx",
            "file_hash": file_hash,
            "images": [],
        },
    )


def _extract_docx_text(payload: bytes) -> str:
    root = ET.fromstring(payload)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [
            node.text or ""
            for node in paragraph.findall(".//w:t", namespace)
        ]
        if parts:
            paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
