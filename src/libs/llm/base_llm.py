"""Base abstractions for text LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


Message = dict[str, str]


@dataclass(frozen=True)
class LLMResponse:
    """Normalized LLM response returned by provider implementations."""

    text: str
    raw: Any | None = None


class BaseLLM(ABC):
    """Common interface for all text LLM providers."""

    @abstractmethod
    def chat(self, messages: list[Message]) -> str:
        """Return the assistant text for a list of chat messages."""
