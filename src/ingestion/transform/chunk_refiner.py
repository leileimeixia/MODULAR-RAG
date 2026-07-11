"""Rule-based and optional LLM chunk refinement."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import Chunk
from libs.llm import BaseLLM, LLMFactory

from .base_transform import BaseTransform


DEFAULT_PROMPT_PATH = Path("config/prompts/chunk_refinement.txt")


class ChunkRefiner(BaseTransform):
    """Clean noisy chunk text and optionally refine it with an LLM."""

    def __init__(
        self,
        settings: Any | None = None,
        llm: BaseLLM | None = None,
        prompt_path: str | Path | None = None,
        use_llm: bool | None = None,
    ) -> None:
        self.settings = settings
        self.use_llm = _resolve_use_llm(settings) if use_llm is None else use_llm
        self.llm = llm
        if self.use_llm and self.llm is None and settings is not None:
            self.llm = LLMFactory.create(settings)
        self.prompt_template = self._load_prompt(prompt_path)

    def transform(self, chunks: list[Chunk], trace: Any | None = None) -> list[Chunk]:
        """Refine chunks independently, falling back per chunk on failures."""
        refined_chunks: list[Chunk] = []
        for chunk in chunks:
            try:
                refined_chunks.append(self._refine_chunk(chunk, trace))
            except Exception as exc:  # pragma: no cover - defensive ingestion fallback
                refined_chunks.append(
                    _replace_chunk(
                        chunk,
                        chunk.text,
                        {
                            "refined_by": "original",
                            "refine_error": str(exc),
                        },
                    )
                )
        if trace is not None:
            trace.record_stage(
                "chunk_refinement",
                method="llm" if self.use_llm else "rule",
                details={"chunk_count": len(refined_chunks)},
            )
        return refined_chunks

    def _refine_chunk(self, chunk: Chunk, trace: Any | None = None) -> Chunk:
        rule_text = self._rule_based_refine(chunk.text)
        metadata = {"refined_by": "rule"}

        if self.use_llm and self.llm is not None:
            llm_text = self._llm_refine(rule_text, trace)
            if llm_text:
                return _replace_chunk(chunk, llm_text, {"refined_by": "llm"})
            metadata["llm_fallback_reason"] = "empty_or_failed_response"

        return _replace_chunk(chunk, rule_text, metadata)

    def _rule_based_refine(self, text: str) -> str:
        """Remove common extraction noise while preserving code fences."""
        if not isinstance(text, str):
            raise TypeError("chunk text must be a string")

        parts = re.split(r"(```[\s\S]*?```)", text)
        cleaned_parts: list[str] = []
        for index, part in enumerate(parts):
            if not part:
                continue
            if index % 2 == 1 and part.startswith("```"):
                cleaned_parts.append(part.strip())
                continue
            cleaned_parts.append(_clean_plain_text(part))
        return "\n\n".join(part for part in cleaned_parts if part).strip()

    def _llm_refine(self, text: str, trace: Any | None = None) -> str | None:
        """Ask an LLM to refine text; return None on graceful failure."""
        if self.llm is None:
            return None
        prompt = self.prompt_template.format(text=text)
        try:
            response = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You refine retrieval chunks without changing facts.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception as exc:
            if trace is not None:
                trace.record_stage(
                    "chunk_refinement_llm_fallback",
                    method="llm",
                    details={"error": str(exc)},
                )
            return None
        return response.strip() or None

    def _load_prompt(self, prompt_path: str | Path | None = None) -> str:
        path = Path(prompt_path) if prompt_path is not None else DEFAULT_PROMPT_PATH
        if path.exists():
            prompt = path.read_text(encoding="utf-8").strip()
        else:
            prompt = "Refine this chunk for retrieval:\n\n{text}"
        if "{text}" not in prompt:
            prompt = f"{prompt}\n\n{{text}}"
        return prompt


def _replace_chunk(chunk: Chunk, text: str, metadata_updates: dict[str, Any]) -> Chunk:
    metadata = dict(chunk.metadata)
    metadata.update(metadata_updates)
    return Chunk(
        id=chunk.id,
        text=text,
        metadata=metadata,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        source_ref=chunk.source_ref,
    )


def _clean_plain_text(text: str) -> str:
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"</?[^>]+>", " ", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if re.fullmatch(r"[-=_*]{3,}", stripped):
            continue
        if re.fullmatch(r"(page|页码)\s*\d+(\s*/\s*\d+)?", stripped, re.IGNORECASE):
            continue
        if re.fullmatch(r"(header|footer)\s*[:：].*", stripped, re.IGNORECASE):
            continue
        lines.append(stripped)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _resolve_use_llm(settings: Any | None) -> bool:
    ingestion = getattr(settings, "ingestion", None)
    chunk_refiner = getattr(ingestion, "chunk_refiner", None)
    if chunk_refiner is not None and hasattr(chunk_refiner, "use_llm"):
        return bool(chunk_refiner.use_llm)
    if isinstance(settings, dict):
        return bool(
            settings.get("ingestion", {})
            .get("chunk_refiner", {})
            .get("use_llm", False)
        )
    return False
