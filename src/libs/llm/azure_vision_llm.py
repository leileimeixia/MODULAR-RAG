"""Azure OpenAI vision chat client."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from core.settings import VisionLLMSettings

from .base_vision_llm import BaseVisionLLM, ImageInput
from .openai_llm import LLMProviderError


class AzureVisionLLM(BaseVisionLLM):
    """Azure OpenAI vision chat provider."""

    def __init__(self, settings: VisionLLMSettings) -> None:
        self.settings = settings
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        if not endpoint:
            endpoint = "https://example-resource.openai.azure.com"
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        deployment = quote(settings.model, safe="")
        self.endpoint = (
            f"{endpoint}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={api_version}"
        )

    def chat_with_image(
        self,
        text: str,
        image_path: ImageInput,
        trace: Any | None = None,
    ) -> str:
        """Call Azure OpenAI with a text prompt and an image."""
        if not text:
            raise LLMProviderError("azure vision prompt text must not be empty")
        image_url = _image_to_data_url(image_path, self.settings.max_image_size)
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["api-key"] = self.settings.api_key

        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=60.0) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMProviderError(
                f"azure vision request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise LLMProviderError(f"azure vision request failed: {reason}") from exc
        except TimeoutError as exc:
            raise LLMProviderError("azure vision request timed out") from exc

        return _parse_vision_response(raw_body)


def _image_to_data_url(image: ImageInput, max_image_size: int) -> str:
    if isinstance(image, bytes):
        data = image
        mime_type = "image/png"
    else:
        path = Path(image)
        if not path.exists():
            raise LLMProviderError(f"azure vision image not found: {path}")
        data = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    if max_image_size <= 0:
        raise LLMProviderError("vision_llm.max_image_size must be greater than 0")

    # Without an image processing dependency, enforce a deterministic byte ceiling.
    # B9 tests this guard; C7 can later add real resize/compression before this layer.
    max_bytes = max_image_size * max_image_size
    if len(data) > max_bytes:
        raise LLMProviderError(
            "azure vision image exceeds configured max_image_size byte budget"
        )

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _parse_vision_response(raw_body: str) -> str:
    try:
        payload: Any = json.loads(raw_body)
        content = payload["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(
            "azure vision response has unexpected shape"
        ) from exc

    if not isinstance(content, str):
        raise LLMProviderError("azure vision response content must be a string")
    return content
