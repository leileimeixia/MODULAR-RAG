"""Tests for settings loading and validation."""

from __future__ import annotations

import textwrap

import pytest

from core.settings import SettingsError, load_settings


def _write_settings(tmp_path, content: str):
    path = tmp_path / "settings.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_load_settings_reads_config_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    path = _write_settings(
        tmp_path,
        """
        llm:
          provider: openai
          model: gpt-5.5
          api_key: ${OPENAI_API_KEY}
        embedding:
          provider: openai
          model: text-embedding-ada-002
          dimensions: 1536
          api_key: ${OPENAI_API_KEY}
        vision_llm:
          enabled: true
          provider: openai
          model: gpt-4o
          api_key: ${OPENAI_API_KEY}
          max_image_size: 2048
        vector_store:
          provider: chroma
          persist_directory: ./data/db/chroma
          collection_name: knowledge_hub
        retrieval:
          dense_top_k: 20
          sparse_top_k: 20
          fusion_top_k: 10
          rrf_k: 60
        rerank:
          enabled: false
          provider: none
          model: ""
          top_k: 5
        evaluation:
          enabled: false
          provider: custom
          backends:
            - ragas
            - custom
        observability:
          log_level: INFO
          trace_enabled: true
          trace_file: ./logs/traces.jsonl
        """,
    )

    settings = load_settings(path)

    assert settings.llm.provider == "openai"
    assert settings.llm.api_key == "test-key"
    assert settings.embedding.dimensions == 1536
    assert settings.vector_store.collection_name == "knowledge_hub"
    assert settings.evaluation.backends == ["ragas", "custom"]


def test_load_settings_reports_missing_required_field(tmp_path) -> None:
    path = _write_settings(
        tmp_path,
        """
        llm:
          provider: openai
          model: gpt-5.5
        embedding:
          provider: ""
          model: text-embedding-ada-002
          dimensions: 1536
        vision_llm:
          enabled: false
          provider: openai
          model: gpt-4o
        vector_store:
          provider: chroma
          persist_directory: ./data/db/chroma
          collection_name: knowledge_hub
        retrieval:
          dense_top_k: 20
          sparse_top_k: 20
          fusion_top_k: 10
          rrf_k: 60
        rerank:
          enabled: false
          provider: none
        evaluation:
          enabled: false
          provider: custom
        observability:
          log_level: INFO
          trace_enabled: true
          trace_file: ./logs/traces.jsonl
        """,
    )

    with pytest.raises(SettingsError, match="embedding.provider"):
        load_settings(path)


def test_load_settings_reports_missing_section(tmp_path) -> None:
    path = _write_settings(
        tmp_path,
        """
        llm:
          provider: openai
          model: gpt-5.5
        """,
    )

    with pytest.raises(SettingsError, match="embedding"):
        load_settings(path)
