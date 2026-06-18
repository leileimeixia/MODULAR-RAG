"""OpenAI-compatible chat completion clients."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.settings import LLMSettings

from .base_llm import BaseLLM, Message


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider call fails."""


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """HTTP settings for an OpenAI-compatible chat completion endpoint."""

    provider: str
    endpoint: str
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    timeout_seconds: float = 60.0


class OpenAICompatibleLLM(BaseLLM):
    """Minimal OpenAI-compatible chat completions client."""

    def __init__(self, settings: LLMSettings, config: OpenAICompatibleConfig) -> None:
        self.settings = settings
        self.config = config

    def chat(self, messages: list[Message]) -> str:
        """Call the configured chat completion endpoint and return assistant text."""
        _validate_messages(messages, self.config.provider)
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
        }
        if self.settings.api_key:
            headers[self.config.auth_header] = (
                f"{self.config.auth_prefix}{self.settings.api_key}"
            )

        request = Request(
            self.config.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMProviderError(
                f"{self.config.provider} chat request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise LLMProviderError(
                f"{self.config.provider} chat request failed: {reason}"
            ) from exc
        except TimeoutError as exc:
            raise LLMProviderError(
                f"{self.config.provider} chat request timed out"
            ) from exc

        return _parse_chat_response(raw_body, self.config.provider)


class OpenAILLM(OpenAICompatibleLLM):
    """OpenAI chat completion provider."""

    def __init__(self, settings: LLMSettings) -> None:
        super().__init__(
            settings,
            OpenAICompatibleConfig(
                provider="openai",
                endpoint="https://api.openai.com/v1/chat/completions",
            ),
        )


def _validate_messages(messages: list[Message], provider: str) -> None:
    if not isinstance(messages, list) or not messages:
        raise LLMProviderError(f"{provider} chat requires a non-empty messages list")

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise LLMProviderError(
                f"{provider} chat message at index {index} must be a mapping"
            )
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not role:
            raise LLMProviderError(
                f"{provider} chat message at index {index} must include role"
            )
        if not isinstance(content, str):
            raise LLMProviderError(
                f"{provider} chat message at index {index} must include string content"
            )


def _parse_chat_response(raw_body: str, provider: str) -> str:
    try:
        payload: Any = json.loads(raw_body)
        content = payload["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(
            f"{provider} chat response has unexpected shape"
        ) from exc

    if not isinstance(content, str):
        raise LLMProviderError(f"{provider} chat response content must be a string")
    return content
