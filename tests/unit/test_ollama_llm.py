"""Tests for the Ollama LLM provider."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from core.settings import LLMSettings
from libs.llm import LLMFactory, LLMProviderError, OllamaLLM
from libs.llm import ollama_llm


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_factory_creates_ollama_provider() -> None:
    llm = LLMFactory.create(LLMSettings(provider="ollama", model="llama3.1"))

    assert isinstance(llm, OllamaLLM)
    assert llm.endpoint == "http://localhost:11434/api/chat"


def test_ollama_chat_posts_native_request_shape(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://unit-test:11434/")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"message": {"role": "assistant", "content": "pong"}})

    monkeypatch.setattr(ollama_llm, "urlopen", fake_urlopen)
    llm = OllamaLLM(
        LLMSettings(
            provider="ollama",
            model="llama3.1",
            temperature=0.2,
            max_tokens=128,
        )
    )

    assert llm.chat([{"role": "user", "content": "ping"}]) == "pong"
    assert captured["url"] == "http://unit-test:11434/api/chat"
    assert captured["payload"] == {
        "model": "llama3.1",
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 128,
        },
    }
    assert captured["headers"]["Content-type"] == "application/json"


def test_ollama_chat_rejects_bad_message_shape() -> None:
    llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3.1"))

    with pytest.raises(LLMProviderError, match="non-empty messages list"):
        llm.chat([])

    with pytest.raises(LLMProviderError, match="string content"):
        llm.chat([{"role": "user", "content": 123}])


def test_ollama_chat_wraps_http_errors_without_leaking_details(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="server error with private path",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(ollama_llm, "urlopen", fake_urlopen)
    llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3.1"))

    with pytest.raises(LLMProviderError, match="HTTP 500") as exc_info:
        llm.chat([{"role": "user", "content": "hi"}])

    assert "private path" not in str(exc_info.value)


def test_ollama_chat_wraps_connection_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(ollama_llm, "urlopen", fake_urlopen)
    llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3.1"))

    with pytest.raises(LLMProviderError, match="ollama chat request failed"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_ollama_chat_rejects_unexpected_response_shape(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"response": "legacy shape"})

    monkeypatch.setattr(ollama_llm, "urlopen", fake_urlopen)
    llm = OllamaLLM(LLMSettings(provider="ollama", model="llama3.1"))

    with pytest.raises(LLMProviderError, match="unexpected shape"):
        llm.chat([{"role": "user", "content": "hi"}])
