"""Default recursive text splitter."""

from __future__ import annotations

import re
from typing import Any

from core.settings import SplitterSettings

from .base_splitter import BaseSplitter


class RecursiveSplitterError(ValueError):
    """Raised when recursive splitter settings or inputs are invalid."""


class RecursiveSplitter(BaseSplitter):
    """Split text by trying larger Markdown boundaries before smaller ones."""

    _separators = ("\n## ", "\n# ", "\n\n", "\n", ". ", " ", "")

    def __init__(self, settings: SplitterSettings) -> None:
        if settings.chunk_size <= 0:
            raise RecursiveSplitterError("splitter.chunk_size must be greater than 0")
        if settings.chunk_overlap < 0:
            raise RecursiveSplitterError(
                "splitter.chunk_overlap must be greater than or equal to 0"
            )
        if settings.chunk_overlap >= settings.chunk_size:
            raise RecursiveSplitterError(
                "splitter.chunk_overlap must be smaller than splitter.chunk_size"
            )
        self.settings = settings

    def split_text(self, text: str, trace: Any | None = None) -> list[str]:
        """Split text into ordered chunks while preserving Markdown code fences."""
        if not isinstance(text, str):
            raise RecursiveSplitterError("split_text expects a string")
        normalized = text.strip()
        if not normalized:
            return []

        protected_blocks = _split_code_fences(normalized)
        chunks: list[str] = []
        for block in protected_blocks:
            if len(block) <= self.settings.chunk_size:
                chunks.append(block)
                continue
            chunks.extend(
                self._split_recursive(block, separators=list(self._separators))
            )
        return _merge_chunks(chunks, self.settings.chunk_size, self.settings.chunk_overlap)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        text = text.strip()
        if len(text) <= self.settings.chunk_size:
            return [text] if text else []
        if not separators:
            return _window_text(
                text,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
            )

        separator = separators[0]
        if separator == "":
            return _window_text(
                text,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
            )

        pieces = _split_keep_separator(text, separator)
        if len(pieces) == 1:
            return self._split_recursive(text, separators[1:])

        results: list[str] = []
        for piece in pieces:
            if len(piece) <= self.settings.chunk_size:
                results.append(piece)
            else:
                results.extend(self._split_recursive(piece, separators[1:]))
        return results


def _split_code_fences(text: str) -> list[str]:
    pattern = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)
    parts = pattern.split(text)
    return [part.strip() for part in parts if part and part.strip()]


def _split_keep_separator(text: str, separator: str) -> list[str]:
    if separator.startswith("\n") and separator.strip().startswith("#"):
        marker = separator.lstrip("\n")
        pieces: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            if line.startswith(marker) and current:
                pieces.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            pieces.append("\n".join(current).strip())
        return [piece for piece in pieces if piece]

    return [piece.strip() for piece in text.split(separator) if piece.strip()]


def _merge_chunks(chunks: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    merged: list[str] = []
    current = ""
    for chunk in chunks:
        if not chunk:
            continue
        if not current:
            current = chunk
            continue

        candidate = f"{current}\n\n{chunk}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        merged.append(current)
        overlap = _tail_overlap(current, chunk_overlap)
        current = f"{overlap}\n\n{chunk}" if overlap else chunk
        if len(current) > chunk_size:
            merged.extend(_window_text(current, chunk_size, chunk_overlap))
            current = ""

    if current:
        merged.append(current)
    return merged


def _window_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    windows: list[str] = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < len(text):
        window = text[start : start + chunk_size].strip()
        if window:
            windows.append(window)
        start += step
    return windows


def _tail_overlap(text: str, chunk_overlap: int) -> str:
    if chunk_overlap <= 0:
        return ""
    return text[-chunk_overlap:].strip()
