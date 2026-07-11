"""Rule-based and optional LLM metadata enrichment."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from core import Chunk
from libs.llm import BaseLLM, LLMFactory

from .base_transform import BaseTransform


class MetadataEnricher(BaseTransform):
    """Add title, summary, and tags metadata to chunks."""

    def __init__(
        self,
        settings: Any | None = None,
        llm: BaseLLM | None = None,
        use_llm: bool | None = None,
    ) -> None:
        self.settings = settings
        self.use_llm = _resolve_use_llm(settings) if use_llm is None else use_llm
        self.llm = llm
        if self.use_llm and self.llm is None and settings is not None:
            self.llm = LLMFactory.create(settings)

    def transform(self, chunks: list[Chunk], trace: Any | None = None) -> list[Chunk]:
        """Enrich chunks independently, keeping ingestion resilient."""
        enriched_chunks: list[Chunk] = []
        for chunk in chunks:
            try:
                enriched_chunks.append(self._enrich_chunk(chunk, trace))
            except Exception as exc:  # pragma: no cover - defensive fallback
                enriched_chunks.append(
                    _replace_chunk_metadata(
                        chunk,
                        {
                            **self._rule_metadata(chunk),
                            "metadata_enriched_by": "rule",
                            "metadata_error": str(exc),
                        },
                    )
                )

        if trace is not None:
            trace.record_stage(
                "metadata_enrichment",
                method="llm" if self.use_llm else "rule",
                details={"chunk_count": len(enriched_chunks)},
            )
        return enriched_chunks

    def _enrich_chunk(self, chunk: Chunk, trace: Any | None = None) -> Chunk:
        rule_metadata = self._rule_metadata(chunk)
        if self.use_llm and self.llm is not None:
            llm_metadata = self._llm_metadata(chunk, rule_metadata, trace)
            if llm_metadata is not None:
                return _replace_chunk_metadata(
                    chunk,
                    {**llm_metadata, "metadata_enriched_by": "llm"},
                )
            return _replace_chunk_metadata(
                chunk,
                {
                    **rule_metadata,
                    "metadata_enriched_by": "rule",
                    "metadata_fallback_reason": "llm_failed_or_invalid",
                },
            )

        return _replace_chunk_metadata(
            chunk,
            {**rule_metadata, "metadata_enriched_by": "rule"},
        )

    def _rule_metadata(self, chunk: Chunk) -> dict[str, Any]:
        text = _normalize_text(chunk.text)
        title = _derive_title(chunk, text)
        summary = _derive_summary(text)
        tags = _derive_tags(text, chunk.metadata)
        return {
            "title": title,
            "summary": summary,
            "tags": tags,
        }

    def _llm_metadata(
        self,
        chunk: Chunk,
        fallback_metadata: dict[str, Any],
        trace: Any | None = None,
    ) -> dict[str, Any] | None:
        if self.llm is None:
            return None

        prompt = (
            "Generate retrieval metadata for this chunk. "
            "Return only JSON with keys title, summary, tags.\n\n"
            f"Fallback metadata: {json.dumps(fallback_metadata, ensure_ascii=False)}\n\n"
            f"Chunk:\n{chunk.text}"
        )
        try:
            response = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You generate concise metadata for RAG chunks.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            return _validate_llm_metadata(json.loads(_extract_json_object(response)))
        except Exception as exc:
            if trace is not None:
                trace.record_stage(
                    "metadata_enrichment_llm_fallback",
                    method="llm",
                    details={"error": str(exc)},
                )
            return None


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


def _derive_title(chunk: Chunk, text: str) -> str:
    existing = chunk.metadata.get("title")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return _truncate(stripped, 80)
    return f"Chunk {chunk.metadata.get('chunk_index', chunk.id)}"


def _derive_summary(text: str) -> str:
    sentence = re.split(r"(?<=[.!?。！？])\s+", text.strip())[0] if text.strip() else ""
    sentence = sentence.lstrip("#").strip()
    if not sentence:
        sentence = "Empty chunk"
    return _truncate(sentence, 240)


def _derive_tags(text: str, metadata: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    doc_type = metadata.get("doc_type")
    if isinstance(doc_type, str) and doc_type:
        candidates.append(doc_type.lower())

    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if word.lower() not in _STOP_WORDS
    ]
    candidates.extend(word for word, _count in Counter(words).most_common(5))

    if not candidates:
        candidates.append("general")

    unique: list[str] = []
    for tag in candidates:
        if tag not in unique:
            unique.append(tag)
    return unique[:5]


def _validate_llm_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("LLM metadata response must be a JSON object")
    title = str(payload.get("title", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    tags = payload.get("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",")]
    if not isinstance(tags, list):
        raise ValueError("LLM metadata tags must be a list")
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    if not title or not summary or not tags:
        raise ValueError("LLM metadata must include non-empty title, summary, and tags")
    return {"title": title, "summary": summary, "tags": tags}


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM metadata response did not contain a JSON object")
    return text[start : end + 1]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "..."


def _resolve_use_llm(settings: Any | None) -> bool:
    ingestion = getattr(settings, "ingestion", None)
    metadata_enricher = getattr(ingestion, "metadata_enricher", None)
    if metadata_enricher is not None and hasattr(metadata_enricher, "use_llm"):
        return bool(metadata_enricher.use_llm)
    if isinstance(settings, dict):
        return bool(
            settings.get("ingestion", {})
            .get("metadata_enricher", {})
            .get("use_llm", False)
        )
    return False


_STOP_WORDS = {
    "and",
    "are",
    "for",
    "from",
    "into",
    "the",
    "this",
    "that",
    "with",
    "your",
}
