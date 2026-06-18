"""DeepSeek OpenAI-compatible chat completion client."""

from __future__ import annotations

from core.settings import LLMSettings

from .openai_llm import OpenAICompatibleConfig, OpenAICompatibleLLM


class DeepSeekLLM(OpenAICompatibleLLM):
    """DeepSeek chat completion provider."""

    def __init__(self, settings: LLMSettings) -> None:
        super().__init__(
            settings,
            OpenAICompatibleConfig(
                provider="deepseek",
                endpoint="https://api.deepseek.com/chat/completions",
            ),
        )
