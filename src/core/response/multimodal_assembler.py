"""Assemble MCP multimodal response content."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from core import RetrievalResult


ContentBlock = dict[str, Any]


class MultimodalAssembler:
    """Append image content blocks for retrieval results with image metadata."""

    def assemble(
        self,
        text_content: list[ContentBlock],
        retrieval_results: list[RetrievalResult],
    ) -> list[ContentBlock]:
        """Return text content followed by image content blocks."""
        content = list(text_content)
        seen_paths: set[str] = set()
        for result in retrieval_results:
            for image in _result_images(result):
                image_path = Path(str(image.get("path", "")))
                if not image_path.is_file():
                    continue
                resolved = str(image_path.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                content.append(_image_content(image_path))
        return content


def _result_images(result: RetrievalResult) -> list[dict[str, Any]]:
    images = result.metadata.get("images", [])
    if images is None:
        return []
    if not isinstance(images, list):
        return []
    image_refs = result.metadata.get("image_refs")
    allowed_ids = set(image_refs) if isinstance(image_refs, list) else None

    normalized: list[dict[str, Any]] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        image_id = image.get("id")
        if allowed_ids is not None and image_id not in allowed_ids:
            continue
        normalized.append(image)
    return normalized


def _image_content(path: Path) -> ContentBlock:
    return {
        "type": "image",
        "mimeType": _mime_type(path),
        "data": base64.b64encode(path.read_bytes()).decode("ascii"),
    }


def _mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"
