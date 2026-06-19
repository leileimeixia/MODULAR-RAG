"""Tests for the default recursive splitter."""

from __future__ import annotations

import pytest

from core.settings import SplitterSettings
from libs.splitter import RecursiveSplitter, RecursiveSplitterError, SplitterFactory


def test_factory_creates_recursive_splitter() -> None:
    splitter = SplitterFactory.create(
        SplitterSettings(provider="recursive", chunk_size=80, chunk_overlap=10)
    )

    assert isinstance(splitter, RecursiveSplitter)


def test_splitter_returns_empty_for_blank_text() -> None:
    splitter = RecursiveSplitter(
        SplitterSettings(provider="recursive", chunk_size=80, chunk_overlap=10)
    )

    assert splitter.split_text(" \n\n ") == []


def test_splitter_splits_long_text_with_overlap() -> None:
    splitter = RecursiveSplitter(
        SplitterSettings(provider="recursive", chunk_size=40, chunk_overlap=8)
    )
    text = " ".join(f"word{i}" for i in range(20))

    chunks = splitter.split_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 40 for chunk in chunks)
    assert chunks[1].startswith(chunks[0][-8:].strip())


def test_splitter_respects_markdown_headings() -> None:
    splitter = RecursiveSplitter(
        SplitterSettings(provider="recursive", chunk_size=90, chunk_overlap=0)
    )
    text = (
        "# Title\n"
        "Intro paragraph with enough text.\n\n"
        "## Setup\n"
        "Install dependencies and configure settings.\n\n"
        "## Usage\n"
        "Run the command and inspect output."
    )

    chunks = splitter.split_text(text)

    assert any(chunk.startswith("# Title") for chunk in chunks)
    assert any(chunk.startswith("## Setup") for chunk in chunks)
    assert any(chunk.startswith("## Usage") for chunk in chunks)


def test_splitter_preserves_small_code_fences() -> None:
    splitter = RecursiveSplitter(
        SplitterSettings(provider="recursive", chunk_size=120, chunk_overlap=0)
    )
    text = (
        "Before\n\n"
        "```python\n"
        "def hello():\n"
        "    return 'world'\n"
        "```\n\n"
        "After"
    )

    chunks = splitter.split_text(text)

    code_chunks = [chunk for chunk in chunks if "```python" in chunk]
    assert len(code_chunks) == 1
    assert "return 'world'" in code_chunks[0]


def test_splitter_rejects_invalid_settings() -> None:
    with pytest.raises(RecursiveSplitterError, match="smaller than"):
        RecursiveSplitter(
            SplitterSettings(provider="recursive", chunk_size=50, chunk_overlap=50)
        )


def test_splitter_rejects_non_string_input() -> None:
    splitter = RecursiveSplitter(
        SplitterSettings(provider="recursive", chunk_size=80, chunk_overlap=10)
    )

    with pytest.raises(RecursiveSplitterError, match="expects a string"):
        splitter.split_text(123)
