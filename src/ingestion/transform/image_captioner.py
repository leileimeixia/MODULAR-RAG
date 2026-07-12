"""Optional image caption generation for chunks with image references."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import Chunk
from libs.llm import BaseVisionLLM, LLMFactory

from .base_transform import BaseTransform


DEFAULT_PROMPT_PATH = Path("config/prompts/image_captioning.txt")


class ImageCaptioner(BaseTransform):
    """Generate captions for chunk image refs with graceful fallback."""

    def __init__(
        self,
        settings: Any | None = None,
        vision_llm: BaseVisionLLM | None = None,
        prompt_path: str | Path | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.settings = settings
        self.enabled = _resolve_enabled(settings) if enabled is None else enabled
        self.vision_llm = vision_llm
        if self.enabled and self.vision_llm is None and settings is not None:
            self.vision_llm = LLMFactory.create_vision_llm(settings)
        self.prompt = self._load_prompt(prompt_path)

    def transform(self, chunks: list[Chunk], trace: Any | None = None) -> list[Chunk]:
        """Caption images referenced by chunks, never blocking ingestion."""
        results = [self._caption_chunk(chunk, trace) for chunk in chunks]
        if trace is not None:
            trace.record_stage(
                "image_captioning",
                method="vision_llm" if self.enabled else "disabled",
                details={"chunk_count": len(results)},
            )
        return results

    def _caption_chunk(self, chunk: Chunk, trace: Any | None = None) -> Chunk:
        image_refs = _chunk_image_refs(chunk)
        if not image_refs:
            return chunk

        if not self.enabled or self.vision_llm is None:
            return _replace_chunk_metadata(
                chunk,
                {
                    "has_unprocessed_images": True,
                    "image_caption_status": "disabled",
                },
            )

        captions: list[dict[str, str]] = []
        failures: list[dict[str, str]] = []
        for image in image_refs:
            image_id = str(image.get("id", ""))
            image_path = image.get("path")
            if not image_id or not image_path:
                failures.append({"image_id": image_id, "error": "missing image id or path"})
                continue
            try:
                caption = self.vision_llm.chat_with_image(
                    self.prompt,
                    image_path,
                    trace=trace,
                ).strip()
            except Exception as exc:
                failures.append({"image_id": image_id, "error": str(exc)})
                continue
            if caption:
                captions.append({"image_id": image_id, "caption": caption})
            else:
                failures.append({"image_id": image_id, "error": "empty caption"})

        updates: dict[str, Any] = {}
        if captions:
            updates["image_captions"] = captions
        if failures:
            updates["has_unprocessed_images"] = True
            updates["image_caption_errors"] = failures
        else:
            updates["has_unprocessed_images"] = False
        return _replace_chunk_metadata(chunk, updates)

    def _load_prompt(self, prompt_path: str | Path | None = None) -> str:
        path = Path(prompt_path) if prompt_path is not None else DEFAULT_PROMPT_PATH
        if path.exists():
            prompt = path.read_text(encoding="utf-8").strip()
        else:
            prompt = "Describe the image for retrieval."
        return prompt or "Describe the image for retrieval."


def _chunk_image_refs(chunk: Chunk) -> list[dict[str, Any]]:
    images = chunk.metadata.get("images", [])
    if isinstance(images, list) and images:
        return [dict(image) for image in images if isinstance(image, dict)]
    return []


def _replace_chunk_metadata(chunk: Chunk, updates: dict[str, Any]) -> Chunk:
    metadata = dict(chunk.metadata)
    metadata.update(updates)
    return Chunk(
        id=chunk.id,
        text=chunk.text,
        metadata=metadata,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        source_ref=chunk.source_ref,
    )


def _resolve_enabled(settings: Any | None) -> bool:
    vision_llm = getattr(settings, "vision_llm", None)
    if vision_llm is not None and hasattr(vision_llm, "enabled"):
        return bool(vision_llm.enabled)
    if isinstance(settings, dict):
        return bool(settings.get("vision_llm", {}).get("enabled", False))
    return False
