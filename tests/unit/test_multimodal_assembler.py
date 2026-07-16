"""Tests for MCP multimodal response assembly."""

from __future__ import annotations

import base64

from core import RetrievalResult
from core.response import MultimodalAssembler, ResponseBuilder


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def _result_with_image(image_path) -> RetrievalResult:
    return RetrievalResult(
        chunk_id="chunk-image",
        score=0.9,
        text="chunk with image",
        metadata={
            "source_path": "docs/image.md",
            "image_refs": ["img-1"],
            "images": [
                {
                    "id": "img-1",
                    "path": str(image_path),
                    "text_offset": 0,
                    "text_length": 10,
                },
                {
                    "id": "img-2",
                    "path": str(image_path),
                    "text_offset": 11,
                    "text_length": 5,
                },
            ],
        },
    )


def test_multimodal_assembler_appends_mcp_image_content(tmp_path) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(PNG_BYTES)

    content = MultimodalAssembler().assemble(
        [{"type": "text", "text": "answer"}],
        [_result_with_image(image_path)],
    )

    assert content[0] == {"type": "text", "text": "answer"}
    assert content[1] == {
        "type": "image",
        "mimeType": "image/png",
        "data": base64.b64encode(PNG_BYTES).decode("ascii"),
    }


def test_multimodal_assembler_skips_missing_images(tmp_path) -> None:
    content = MultimodalAssembler().assemble(
        [{"type": "text", "text": "answer"}],
        [_result_with_image(tmp_path / "missing.png")],
    )

    assert content == [{"type": "text", "text": "answer"}]


def test_response_builder_includes_image_content(tmp_path) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(PNG_BYTES)

    response = ResponseBuilder().build([_result_with_image(image_path)], query="diagram")

    assert response["content"][0]["type"] == "text"
    assert response["content"][1]["type"] == "image"
    assert response["content"][1]["mimeType"] == "image/png"
    assert response["content"][1]["data"] == base64.b64encode(PNG_BYTES).decode("ascii")
