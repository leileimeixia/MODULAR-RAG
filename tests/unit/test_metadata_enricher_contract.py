"""Tests for metadata enrichment transform."""

from __future__ import annotations

import json

from core import Chunk
from core.trace import TraceContext
from ingestion.transform import MetadataEnricher
from libs.llm import BaseLLM


class FakeLLM(BaseLLM):
    def __init__(self, response: str, fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        if self.fail:
            raise RuntimeError("llm unavailable")
        return self.response


def _chunk(text: str | None = None) -> Chunk:
    text = text or "# Setup Guide\nInstall dependencies and configure OpenAI embeddings."
    return Chunk(
        id="chunk-1",
        text=text,
        metadata={
            "source_path": "docs/setup.md",
            "doc_type": "markdown",
            "chunk_index": 0,
        },
        start_offset=0,
        end_offset=len(text),
        source_ref="doc-1",
    )


def test_rule_mode_adds_non_empty_title_summary_and_tags() -> None:
    result = MetadataEnricher().transform([_chunk()])[0]

    assert result.metadata["title"] == "Setup Guide Install dependencies and configure OpenAI embeddings."
    assert result.metadata["summary"] == "Setup Guide Install dependencies and configure OpenAI embeddings."
    assert result.metadata["tags"]
    assert result.metadata["metadata_enriched_by"] == "rule"


def test_rule_mode_preserves_existing_metadata() -> None:
    result = MetadataEnricher().transform([_chunk()])[0]

    assert result.metadata["source_path"] == "docs/setup.md"
    assert result.metadata["doc_type"] == "markdown"
    assert result.metadata["chunk_index"] == 0


def test_existing_title_is_reused_by_rule_mode() -> None:
    chunk = Chunk(
        id="chunk-1",
        text="Body text about vector search.",
        metadata={"source_path": "docs/vector.md", "title": "Vector Search"},
        start_offset=0,
        end_offset=30,
    )

    result = MetadataEnricher().transform([chunk])[0]

    assert result.metadata["title"] == "Vector Search"
    assert result.metadata["summary"] == "Body text about vector search."


def test_llm_mode_uses_mock_llm_metadata() -> None:
    payload = {
        "title": "LLM Title",
        "summary": "A semantic summary from the model.",
        "tags": ["rag", "metadata"],
    }
    llm = FakeLLM(json.dumps(payload))

    result = MetadataEnricher(llm=llm, use_llm=True).transform([_chunk()])[0]

    assert result.metadata["title"] == "LLM Title"
    assert result.metadata["summary"] == "A semantic summary from the model."
    assert result.metadata["tags"] == ["rag", "metadata"]
    assert result.metadata["metadata_enriched_by"] == "llm"
    assert "Chunk:" in llm.messages[0][-1]["content"]


def test_llm_mode_extracts_json_from_wrapped_response() -> None:
    llm = FakeLLM(
        'Here is metadata: {"title": "Wrapped", "summary": "Wrapped summary", '
        '"tags": ["wrapped"]}'
    )

    result = MetadataEnricher(llm=llm, use_llm=True).transform([_chunk()])[0]

    assert result.metadata["title"] == "Wrapped"
    assert result.metadata["tags"] == ["wrapped"]


def test_llm_failure_falls_back_to_rule_metadata() -> None:
    result = MetadataEnricher(llm=FakeLLM("{}", fail=True), use_llm=True).transform(
        [_chunk()]
    )[0]

    assert result.metadata["metadata_enriched_by"] == "rule"
    assert result.metadata["metadata_fallback_reason"] == "llm_failed_or_invalid"
    assert result.metadata["title"]
    assert result.metadata["summary"]
    assert result.metadata["tags"]


def test_invalid_llm_json_falls_back_to_rule_metadata() -> None:
    result = MetadataEnricher(llm=FakeLLM("not json"), use_llm=True).transform([_chunk()])[0]

    assert result.metadata["metadata_enriched_by"] == "rule"
    assert result.metadata["metadata_fallback_reason"] == "llm_failed_or_invalid"


def test_transform_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-meta")

    MetadataEnricher().transform([_chunk()], trace=trace)

    assert trace.stages[-1].name == "metadata_enrichment"
    assert trace.stages[-1].method == "rule"
    assert trace.stages[-1].details == {"chunk_count": 1}


def test_settings_dict_can_enable_llm_mode() -> None:
    llm = FakeLLM(
        json.dumps(
            {"title": "Dict Enabled", "summary": "Enabled by settings.", "tags": ["cfg"]}
        )
    )

    result = MetadataEnricher(
        settings={"ingestion": {"metadata_enricher": {"use_llm": True}}},
        llm=llm,
    ).transform([_chunk()])[0]

    assert result.metadata["metadata_enriched_by"] == "llm"
    assert result.metadata["title"] == "Dict Enabled"
