"""Azure OpenAI chat completion client."""

from __future__ import annotations

import os
from urllib.parse import quote

from core.settings import LLMSettings

from .openai_llm import OpenAICompatibleConfig, OpenAICompatibleLLM


class AzureLLM(OpenAICompatibleLLM):
    """Azure OpenAI chat completion provider."""

    def __init__(self, settings: LLMSettings) -> None:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        if not endpoint:
            endpoint = "https://example-resource.openai.azure.com"
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        deployment = quote(settings.model, safe="")
        super().__init__(
            settings,
            OpenAICompatibleConfig(
                provider="azure",
                endpoint=(
                    f"{endpoint}/openai/deployments/{deployment}/chat/completions"
                    f"?api-version={api_version}"
                ),
                auth_header="api-key",
                auth_prefix="",
            ),
        )
