"""Azure OpenAI embedding client."""

from __future__ import annotations

import os
from urllib.parse import quote

from core.settings import EmbeddingSettings

from .openai_embedding import OpenAICompatibleEmbedding, OpenAIEmbeddingConfig


class AzureEmbedding(OpenAICompatibleEmbedding):
    """Azure OpenAI embedding provider."""

    def __init__(self, settings: EmbeddingSettings) -> None:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        if not endpoint:
            endpoint = "https://example-resource.openai.azure.com"
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        deployment = quote(settings.model, safe="")
        super().__init__(
            settings,
            OpenAIEmbeddingConfig(
                provider="azure",
                endpoint=(
                    f"{endpoint}/openai/deployments/{deployment}/embeddings"
                    f"?api-version={api_version}"
                ),
                auth_header="api-key",
                auth_prefix="",
            ),
        )
