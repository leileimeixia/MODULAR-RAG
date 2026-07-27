"""Streamlit dashboard smoke tests using AppTest when Streamlit is installed."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

try:
    from streamlit.testing.v1 import AppTest  # type: ignore[import-not-found]
except ImportError:
    AppTest = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_pages_render_without_python_exceptions(tmp_path) -> None:
    if AppTest is None:
        pytest.skip("Streamlit is optional for non-dashboard test environments.")

    smoke_app = tmp_path / "dashboard_smoke_app.py"
    smoke_app.write_text(_smoke_app_source(), encoding="utf-8")

    app = AppTest.from_file(str(smoke_app))
    app.run(timeout=10)

    assert not app.exception
    assert [title.value for title in app.title] == [
        "System Overview",
        "Data Browser",
        "Ingestion Manager",
        "Ingestion Traces",
        "Query Traces",
        "Evaluation Panel",
    ]


def _smoke_app_source() -> str:
    src_root = PROJECT_ROOT / "src"
    return textwrap.dedent(
        f'''
        from __future__ import annotations

        import sys
        from pathlib import Path

        import streamlit as st

        sys.path.insert(0, {str(src_root)!r})

        from observability.dashboard.pages import (
            data_browser,
            evaluation_panel,
            ingestion_manager,
            ingestion_traces,
            overview,
            query_traces,
        )


        class FakeConfigService:
            def overview(self):
                return {{
                    "settings_path": "config/settings.yaml",
                    "components": [
                        {{
                            "name": "LLM",
                            "provider": "openai",
                            "model": "gpt-5.5",
                            "status": "configured",
                            "details": {{"provider": "openai"}},
                        }}
                    ],
                    "data_stats": {{
                        "record_count": 2,
                        "source_count": 1,
                        "collection_name": "docs",
                        "status": "available",
                        "persist_directory": "data/db/chroma",
                        "collection_file": "data/db/chroma/docs.json",
                    }},
                }}


        class FakeDataService:
            def list_collections(self):
                return ["docs"]

            def list_documents(self, collection=None, query=""):
                return [
                    {{
                        "doc_id": "doc-1",
                        "source_path": "docs/guide.md",
                        "source_name": "guide.md",
                        "collection": "docs",
                        "file_hash": "hash-1",
                        "chunk_count": 1,
                        "image_count": 0,
                        "processed_at": "",
                    }}
                ]

            def collection_stats(self, collection=None):
                return {{"document_count": 1, "chunk_count": 1, "image_count": 0}}

            def get_document_detail(self, doc_id):
                return {{
                    "info": {{
                        "doc_id": "doc-1",
                        "source_path": "docs/guide.md",
                        "source_name": "guide.md",
                        "file_hash": "hash-1",
                    }},
                    "metadata": {{"title": "Guide"}},
                    "chunks": [
                        {{
                            "id": "chunk-a",
                            "preview": "alpha",
                            "text": "alpha",
                            "metadata": {{"source_path": "docs/guide.md"}},
                        }}
                    ],
                    "images": [],
                }}


        class FakeIngestionService:
            def list_documents(self, collection=None):
                return [
                    {{
                        "source_name": "guide.md",
                        "source_path": "docs/guide.md",
                        "collection": "docs",
                        "chunk_count": 1,
                        "image_count": 0,
                    }}
                ]


        class FakeTraceService:
            def list_ingestion_traces(self):
                return [
                    {{
                        "trace_id": "ingestion-1",
                        "trace_type": "ingestion",
                        "started_at": "2026-07-27T00:00:00Z",
                        "finished_at": "2026-07-27T00:00:01Z",
                        "total_elapsed_ms": 10.0,
                        "stage_count": 1,
                        "status": "completed",
                        "source_path": "docs/guide.md",
                        "document_id": "doc-1",
                    }}
                ]

            def get_ingestion_trace(self, trace_id):
                return {{
                    "trace_id": trace_id,
                    "trace_type": "ingestion",
                    "started_at": "2026-07-27T00:00:00Z",
                    "finished_at": "2026-07-27T00:00:01Z",
                    "total_elapsed_ms": 10.0,
                    "stage_count": 1,
                    "status": "completed",
                    "source_path": "docs/guide.md",
                    "stages": [
                        {{
                            "index": 1,
                            "name": "load",
                            "method": "PdfLoader",
                            "elapsed_ms": 10.0,
                            "failed": False,
                            "details": {{"source_path": "docs/guide.md"}},
                        }}
                    ],
                }}

            def list_query_traces(self):
                return [
                    {{
                        "trace_id": "query-1",
                        "trace_type": "query",
                        "started_at": "2026-07-27T00:00:00Z",
                        "finished_at": "2026-07-27T00:00:01Z",
                        "total_elapsed_ms": 12.0,
                        "stage_count": 1,
                        "status": "completed",
                        "query": "alpha",
                    }}
                ]

            def get_query_trace(self, trace_id):
                return {{
                    "trace_id": trace_id,
                    "trace_type": "query",
                    "started_at": "2026-07-27T00:00:00Z",
                    "finished_at": "2026-07-27T00:00:01Z",
                    "total_elapsed_ms": 12.0,
                    "stage_count": 1,
                    "status": "completed",
                    "retrieval_comparison": [
                        {{
                            "route": "Dense",
                            "stage": "dense_retrieval",
                            "method": "DenseRetriever",
                            "elapsed_ms": 5.0,
                            "result_count": 1,
                            "failed": False,
                        }}
                    ],
                    "rerank_summary": {{"method": "NoneReranker", "result_count": 1}},
                    "stages": [
                        {{
                            "index": 1,
                            "name": "dense_retrieval",
                            "method": "DenseRetriever",
                            "elapsed_ms": 5.0,
                            "failed": False,
                            "details": {{"result_count": 1}},
                        }}
                    ],
                }}


        class FakeEvaluationService:
            def run_evaluation(self, test_set_path, top_k=None):
                return {{
                    "metrics": {{"hit_rate": 1.0, "mrr": 1.0}},
                    "case_results": [
                        {{
                            "query": "alpha",
                            "retrieved_ids": ["chunk-a"],
                            "expected_chunk_ids": ["chunk-a"],
                            "metrics": {{"hit_rate": 1.0, "mrr": 1.0}},
                            "details": {{"top_k": top_k}},
                        }}
                    ],
                    "details": {{"test_set_path": str(test_set_path), "case_count": 1}},
                }}


        overview.render(st, config_service=FakeConfigService())
        data_browser.render(st, data_service=FakeDataService())
        ingestion_manager.render(st, ingestion_service=FakeIngestionService())
        ingestion_traces.render(st, trace_service=FakeTraceService())
        query_traces.render(st, trace_service=FakeTraceService())
        evaluation_panel.render(st, evaluation_service=FakeEvaluationService())
        '''
    )
