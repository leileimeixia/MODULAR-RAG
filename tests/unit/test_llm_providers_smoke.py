"""Smoke tests for OpenAI-compatible LLM providers."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from core.settings import LLMSettings
from libs.llm import (
    AzureLLM,
    DeepSeekLLM,
    LLMFactory,
    LLMProviderError,
    OpenAILLM,
)
from libs.llm import openai_llm


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_factory_routes_openai_compatible_providers() -> None:
    assert isinstance(
        LLMFactory.create(LLMSettings(provider="openai", model="gpt-5.5")),
        OpenAILLM,
    )
    assert isinstance(
        LLMFactory.create(LLMSettings(provider="azure", model="deployment")),
        AzureLLM,
    )
    assert isinstance(
        LLMFactory.create(LLMSettings(provider="deepseek", model="deepseek-chat")),
        DeepSeekLLM,
    )


def test_openai_chat_posts_expected_shape(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {"choices": [{"message": {"content": "hello from model"}}]}
        )

    monkeypatch.setattr(openai_llm, "urlopen", fake_urlopen)
    llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-5.5", api_key="secret"))

    result = llm.chat([{"role": "user", "content": "hello"}])

    assert result == "hello from model"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["payload"]["model"] == "gpt-5.5"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_azure_uses_deployment_url_and_api_key_header(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://unit-test.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-01-01")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeHTTPResponse({"choices": [{"message": {"content": "azure"}}]})

    monkeypatch.setattr(openai_llm, "urlopen", fake_urlopen)
    llm = AzureLLM(LLMSettings(provider="azure", model="my deployment", api_key="key"))

    assert llm.chat([{"role": "user", "content": "hi"}]) == "azure"
    assert captured["url"] == (
        "https://unit-test.openai.azure.com/openai/deployments/"
        "my%20deployment/chat/completions?api-version=2024-01-01"
    )
    assert captured["headers"]["Api-key"] == "key"


def test_chat_rejects_bad_message_shape() -> None:
    llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-5.5"))

    with pytest.raises(LLMProviderError, match="openai chat requires"):
        llm.chat([])

    with pytest.raises(LLMProviderError, match="string content"):
        llm.chat([{"role": "user", "content": 123}])


def test_chat_wraps_http_errors_without_leaking_api_key(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized secret-key",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(openai_llm, "urlopen", fake_urlopen)
    llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-5.5", api_key="secret"))

    with pytest.raises(LLMProviderError) as exc_info:
        llm.chat([{"role": "user", "content": "hi"}])

    assert "HTTP 401" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_chat_wraps_connection_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(openai_llm, "urlopen", fake_urlopen)
    llm = DeepSeekLLM(LLMSettings(provider="deepseek", model="deepseek-chat"))

    with pytest.raises(LLMProviderError, match="deepseek chat request failed"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_chat_rejects_unexpected_response_shape(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"not_choices": []})

    monkeypatch.setattr(openai_llm, "urlopen", fake_urlopen)
    llm = OpenAILLM(LLMSettings(provider="openai", model="gpt-5.5"))

    with pytest.raises(LLMProviderError, match="unexpected shape"):
        llm.chat([{"role": "user", "content": "hi"}])
