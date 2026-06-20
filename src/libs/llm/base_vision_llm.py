"""Base abstractions for vision-capable LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ImageInput = str | Path | bytes


@dataclass(frozen=True)
class VisionLLMResponse:
    """Normalized response returned by vision LLM providers."""

    text: str
    raw: Any | None = None


class BaseVisionLLM(ABC):
    """Common interface for multimodal LLM providers."""

    @abstractmethod
    def chat_with_image(
        self,
        text: str,
        image_path: ImageInput,
        trace: Any | None = None,
    ) -> str:
        """Return assistant text for a text prompt plus an image input."""
