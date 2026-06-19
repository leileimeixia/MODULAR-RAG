"""Ollama local chat client."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.settings import LLMSettings

from .base_llm import BaseLLM, Message
from .openai_llm import LLMProviderError


class OllamaLLM(BaseLLM):
    """LLM provider for Ollama's native `/api/chat` endpoint."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.endpoint = f"{self.base_url}/api/chat"

    def chat(self, messages: list[Message]) -> str:
        """Call Ollama chat and return assistant text."""
        _validate_messages(messages)
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.settings.temperature,
                "num_predict": self.settings.max_tokens,
            },
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60.0) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMProviderError(
                f"ollama chat request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise LLMProviderError(f"ollama chat request failed: {reason}") from exc
        except TimeoutError as exc:
            raise LLMProviderError("ollama chat request timed out") from exc

        return _parse_ollama_response(raw_body)


def _validate_messages(messages: list[Message]) -> None:
    if not isinstance(messages, list) or not messages:
        raise LLMProviderError("ollama chat requires a non-empty messages list")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise LLMProviderError(
                f"ollama chat message at index {index} must be a mapping"
            )
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not role:
            raise LLMProviderError(
                f"ollama chat message at index {index} must include role"
            )
        if not isinstance(content, str):
            raise LLMProviderError(
                f"ollama chat message at index {index} must include string content"
            )


def _parse_ollama_response(raw_body: str) -> str:
    try:
        payload: Any = json.loads(raw_body)
        content = payload["message"]["content"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LLMProviderError("ollama chat response has unexpected shape") from exc

    if not isinstance(content, str):
        raise LLMProviderError("ollama chat response content must be a string")
    return content
