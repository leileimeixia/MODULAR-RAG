"""PDF loader implementation."""

from __future__ import annotations

import re
import zlib
from pathlib import Path

from core import Document

from .base_loader import BaseLoader, LoaderError
from .file_integrity import compute_sha256


class PdfLoader(BaseLoader):
    """Load PDF text into a Document with safe image-extraction fallback."""

    def load(self, path: str | Path) -> Document:
        pdf_path = Path(path)
        if not pdf_path.is_file():
            raise LoaderError(f"PDF file does not exist: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise LoaderError(f"expected a .pdf file, got: {pdf_path}")

        file_hash = compute_sha256(pdf_path)
        text = self._extract_text(pdf_path)
        if not text:
            raise LoaderError(f"no extractable text found in PDF: {pdf_path}")

        return Document(
            id=file_hash,
            text=text,
            metadata={
                "source_path": str(pdf_path),
                "doc_type": "pdf",
                "file_hash": file_hash,
                "images": [],
            },
        )

    def _extract_text(self, path: Path) -> str:
        pypdf_text = self._extract_with_pypdf(path)
        if pypdf_text:
            return pypdf_text
        return self._extract_with_builtin_parser(path)

    def _extract_with_pypdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ImportError:
            return ""

        reader = PdfReader(str(path))
        page_texts = [page.extract_text() or "" for page in reader.pages]
        return _normalize_text("\n".join(page_texts))

    def _extract_with_builtin_parser(self, path: Path) -> str:
        raw = path.read_bytes()
        streams = _extract_streams(raw)
        chunks: list[str] = []
        for stream in streams or [raw]:
            chunks.extend(_extract_pdf_strings(stream))
        return _normalize_text("\n".join(chunks))


def _extract_streams(raw: bytes) -> list[bytes]:
    streams: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL):
        stream = match.group(1)
        try:
            streams.append(zlib.decompress(stream))
        except zlib.error:
            streams.append(stream)
    return streams


def _extract_pdf_strings(raw: bytes) -> list[str]:
    texts: list[str] = []
    for match in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj", raw):
        texts.append(_decode_pdf_literal(match.group(0).rsplit(b")", 1)[0][1:]))
    for match in re.finditer(rb"\[(.*?)\]\s*TJ", raw, re.DOTALL):
        texts.extend(
            _decode_pdf_literal(item[1:-1])
            for item in re.findall(rb"\((?:\\.|[^\\()])*\)", match.group(1))
        )
    return texts


def _decode_pdf_literal(value: bytes) -> str:
    replacements = {
        rb"\(": b"(",
        rb"\)": b")",
        rb"\\": b"\\",
        rb"\n": b"\n",
        rb"\r": b"\r",
        rb"\t": b"\t",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value.decode("utf-8", errors="ignore")


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
