"""Tests for image caption transform fallback behavior."""

from __future__ import annotations

from pathlib import Path

from core import Chunk
from core.trace import TraceContext
from ingestion.transform import ImageCaptioner
from libs.llm import BaseVisionLLM


class FakeVisionLLM(BaseVisionLLM):
    def __init__(self, response: str = "A useful image caption.", fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.calls: list[tuple[str, str | Path | bytes]] = []

    def chat_with_image(self, text: str, image_path: str | Path | bytes, trace=None) -> str:
        self.calls.append((text, image_path))
        if self.fail:
            raise RuntimeError("vision failed")
        return self.response


def _chunk_with_image() -> Chunk:
    return Chunk(
        id="chunk-1",
        text="See [IMAGE: img-1]",
        metadata={
            "source_path": "docs/sample.pdf",
            "image_refs": ["img-1"],
            "images": [
                {
                    "id": "img-1",
                    "path": "data/images/doc/img-1.png",
                    "page": 0,
                    "text_offset": 4,
                    "text_length": 14,
                    "position": {},
                }
            ],
        },
        start_offset=0,
        end_offset=18,
        source_ref="doc-1",
    )


def test_disabled_captioner_keeps_image_refs_and_marks_unprocessed() -> None:
    chunk = _chunk_with_image()

    result = ImageCaptioner(enabled=False).transform([chunk])[0]

    assert result.metadata["image_refs"] == ["img-1"]
    assert result.metadata["has_unprocessed_images"] is True
    assert result.metadata["image_caption_status"] == "disabled"
    assert "image_captions" not in result.metadata


def test_enabled_captioner_generates_caption_with_mock_vision_llm(tmp_path) -> None:
    prompt_path = tmp_path / "image_prompt.txt"
    prompt_path.write_text("Describe for retrieval", encoding="utf-8")
    vision = FakeVisionLLM(response="A diagram about RAG.")

    result = ImageCaptioner(
        vision_llm=vision,
        prompt_path=prompt_path,
        enabled=True,
    ).transform([_chunk_with_image()])[0]

    assert result.metadata["image_captions"] == [
        {"image_id": "img-1", "caption": "A diagram about RAG."}
    ]
    assert result.metadata["has_unprocessed_images"] is False
    assert vision.calls == [("Describe for retrieval", "data/images/doc/img-1.png")]


def test_captioner_returns_chunk_unchanged_without_images() -> None:
    chunk = Chunk(
        id="chunk-no-image",
        text="plain text",
        metadata={"source_path": "docs/plain.md"},
        start_offset=0,
        end_offset=10,
    )

    result = ImageCaptioner(enabled=True, vision_llm=FakeVisionLLM()).transform([chunk])[0]

    assert result == chunk


def test_vision_failure_marks_unprocessed_without_blocking() -> None:
    result = ImageCaptioner(
        enabled=True,
        vision_llm=FakeVisionLLM(fail=True),
    ).transform([_chunk_with_image()])[0]

    assert result.metadata["has_unprocessed_images"] is True
    assert result.metadata["image_caption_errors"][0]["image_id"] == "img-1"
    assert "vision failed" in result.metadata["image_caption_errors"][0]["error"]


def test_empty_caption_marks_failure() -> None:
    chunk = Chunk(
        id="chunk-1",
        text="See image",
        metadata={
            "source_path": "docs/sample.pdf",
            "image_refs": ["img-1"],
            "images": [
                {
                    "id": "img-1",
                    "path": "data/images/doc/img-1.png",
                    "page": 0,
                    "text_offset": 0,
                    "text_length": 14,
                    "position": {},
                }
            ],
        },
        start_offset=0,
        end_offset=9,
    )

    result = ImageCaptioner(enabled=True, vision_llm=FakeVisionLLM(response="")).transform(
        [chunk]
    )[0]

    assert result.metadata["has_unprocessed_images"] is True
    assert result.metadata["image_caption_errors"][0]["error"] == "empty caption"


def test_captioner_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-image")

    ImageCaptioner(enabled=False).transform([_chunk_with_image()], trace=trace)

    assert trace.stages[-1].name == "image_captioning"
    assert trace.stages[-1].method == "disabled"
    assert trace.stages[-1].details == {"chunk_count": 1}
