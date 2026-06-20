"""Tests for the Azure Vision LLM provider."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError

import pytest

from core.settings import VisionLLMSettings
from libs.llm import AzureVisionLLM, LLMFactory, LLMProviderError
from libs.llm import azure_vision_llm


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _settings(max_image_size: int = 2048) -> VisionLLMSettings:
    return VisionLLMSettings(
        enabled=True,
        provider="azure",
        model="gpt-4o",
        api_key="key",
        max_image_size=max_image_size,
    )


def test_factory_creates_azure_vision_provider() -> None:
    vision_llm = LLMFactory.create_vision_llm(_settings())

    assert isinstance(vision_llm, AzureVisionLLM)


def test_azure_vision_posts_expected_payload_from_bytes(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://unit-test.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-01-01")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {"choices": [{"message": {"content": "caption text"}}]}
        )

    monkeypatch.setattr(azure_vision_llm, "urlopen", fake_urlopen)
    vision_llm = AzureVisionLLM(_settings())

    result = vision_llm.chat_with_image("describe", b"image-bytes")

    assert result == "caption text"
    assert captured["url"] == (
        "https://unit-test.openai.azure.com/openai/deployments/"
        "gpt-4o/chat/completions?api-version=2024-01-01"
    )
    assert captured["headers"]["Api-key"] == "key"
    content = captured["payload"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(b"image-bytes").decode("ascii")
    )


def test_azure_vision_supports_image_path(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"jpg-bytes")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"choices": [{"message": {"content": "caption"}}]})

    monkeypatch.setattr(azure_vision_llm, "urlopen", fake_urlopen)
    vision_llm = AzureVisionLLM(_settings())

    assert vision_llm.chat_with_image("describe", image_path) == "caption"
    image_url = captured["payload"]["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")


def test_azure_vision_rejects_oversized_image_bytes() -> None:
    vision_llm = AzureVisionLLM(_settings(max_image_size=2))

    with pytest.raises(LLMProviderError, match="max_image_size byte budget"):
        vision_llm.chat_with_image("describe", b"12345")


def test_azure_vision_rejects_missing_image_path(tmp_path) -> None:
    vision_llm = AzureVisionLLM(_settings())

    with pytest.raises(LLMProviderError, match="image not found"):
        vision_llm.chat_with_image("describe", tmp_path / "missing.png")


def test_azure_vision_wraps_http_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized secret",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(azure_vision_llm, "urlopen", fake_urlopen)
    vision_llm = AzureVisionLLM(_settings())

    with pytest.raises(LLMProviderError) as exc_info:
        vision_llm.chat_with_image("describe", b"image")

    assert "HTTP 401" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_azure_vision_wraps_connection_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(azure_vision_llm, "urlopen", fake_urlopen)
    vision_llm = AzureVisionLLM(_settings())

    with pytest.raises(LLMProviderError, match="azure vision request failed"):
        vision_llm.chat_with_image("describe", b"image")


def test_azure_vision_rejects_unexpected_response_shape(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"not_choices": []})

    monkeypatch.setattr(azure_vision_llm, "urlopen", fake_urlopen)
    vision_llm = AzureVisionLLM(_settings())

    with pytest.raises(LLMProviderError, match="unexpected shape"):
        vision_llm.chat_with_image("describe", b"image")
