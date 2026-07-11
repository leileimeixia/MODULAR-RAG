"""Tests for chunk refinement transforms."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import Chunk
from core.trace import TraceContext
from ingestion.transform import BaseTransform, ChunkRefiner, TransformError
from libs.llm import BaseLLM


class FakeLLM(BaseLLM):
    def __init__(self, response: str = "LLM refined text", fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        if self.fail:
            raise RuntimeError("llm down")
        return self.response


def _chunk(text: str = "Hello   world") -> Chunk:
    return Chunk(
        id="chunk-1",
        text=text,
        metadata={"source_path": "docs/sample.md"},
        start_offset=0,
        end_offset=len(text),
        source_ref="doc-1",
    )


def _fixtures() -> dict[str, str]:
    return json.loads(Path("tests/fixtures/noisy_chunks.json").read_text(encoding="utf-8"))


def test_rule_based_refine_removes_headers_footers_and_separators() -> None:
    refiner = ChunkRefiner()

    result = refiner.transform([_chunk(_fixtures()["typical_noise_scenario"])])[0]

    assert "Header:" not in result.text
    assert "Footer:" not in result.text
    assert "Page 1" not in result.text
    assert "---" not in result.text
    assert "This is useful content. It has extra spaces." in result.text
    assert result.metadata["refined_by"] == "rule"


def test_rule_based_refine_normalizes_whitespace() -> None:
    result = ChunkRefiner().transform([_chunk(_fixtures()["excessive_whitespace"])])[0]

    assert result.text == "Alpha beta gamma\n\nDelta"


def test_rule_based_refine_removes_html_and_format_markers() -> None:
    result = ChunkRefiner().transform([_chunk(_fixtures()["format_markers"])])[0]

    assert "comment" not in result.text
    assert "<p>" not in result.text
    assert "====" not in result.text
    assert "Important content" in result.text


def test_rule_based_refine_preserves_code_fences() -> None:
    result = ChunkRefiner().transform([_chunk(_fixtures()["code_blocks"])])[0]

    assert "```python" in result.text
    assert "    return 'world'" in result.text


def test_clean_text_is_not_over_cleaned() -> None:
    text = _fixtures()["clean_text"]
    result = ChunkRefiner().transform([_chunk(text)])[0]

    assert result.text == text


def test_llm_mode_uses_mock_llm_and_marks_metadata(tmp_path) -> None:
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Please refine:\n{text}", encoding="utf-8")
    llm = FakeLLM(response="Better retrieval text")
    refiner = ChunkRefiner(llm=llm, prompt_path=prompt_path, use_llm=True)

    result = refiner.transform([_chunk("Raw   text")])[0]

    assert result.text == "Better retrieval text"
    assert result.metadata["refined_by"] == "llm"
    assert "Raw text" in llm.messages[0][-1]["content"]


def test_llm_failure_falls_back_to_rule_result() -> None:
    refiner = ChunkRefiner(llm=FakeLLM(fail=True), use_llm=True)

    result = refiner.transform([_chunk("Raw   text")])[0]

    assert result.text == "Raw text"
    assert result.metadata["refined_by"] == "rule"
    assert result.metadata["llm_fallback_reason"] == "empty_or_failed_response"


def test_transform_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-1")

    ChunkRefiner().transform([_chunk()], trace=trace)

    assert trace.trace_id == "trace-1"
    assert trace.stages[-1].name == "chunk_refinement"
    assert trace.stages[-1].details == {"chunk_count": 1}


def test_single_chunk_error_does_not_block_other_chunks(monkeypatch) -> None:
    refiner = ChunkRefiner()
    original = refiner._rule_based_refine

    def sometimes_fail(text: str) -> str:
        if "bad" in text:
            raise RuntimeError("bad chunk")
        return original(text)

    monkeypatch.setattr(refiner, "_rule_based_refine", sometimes_fail)

    results = refiner.transform([_chunk("bad"), _chunk("good   text")])

    assert results[0].text == "bad"
    assert results[0].metadata["refined_by"] == "original"
    assert results[1].text == "good text"
    assert results[1].metadata["refined_by"] == "rule"


def test_base_transform_requires_transform_implementation() -> None:
    with pytest.raises(TypeError):
        BaseTransform()


def test_transform_error_is_value_error() -> None:
    assert issubclass(TransformError, ValueError)
