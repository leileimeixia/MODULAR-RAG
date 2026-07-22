"""Tests for dashboard app registration."""

from __future__ import annotations

from observability.dashboard import app
from observability.dashboard.pages import (
    data_browser,
    evaluation_panel,
    ingestion_manager,
    ingestion_traces,
    query_traces,
)


def test_dashboard_registers_six_pages() -> None:
    pages = app.page_specs()

    assert [page.title for page in pages] == [
        "System Overview",
        "Data Browser",
        "Ingestion Manager",
        "Ingestion Traces",
        "Query Traces",
        "Evaluation Panel",
    ]


def test_placeholder_pages_render_without_streamlit_dependency() -> None:
    fake_st = _FakeStreamlit()

    ingestion_manager.render(fake_st)
    ingestion_traces.render(fake_st)
    query_traces.render(fake_st)
    evaluation_panel.render(fake_st)

    assert fake_st.titles == [
        "Ingestion Manager",
        "Ingestion Traces",
        "Query Traces",
        "Evaluation Panel",
    ]
    assert len(fake_st.messages) == 4


def test_data_browser_page_renders_document_detail() -> None:
    fake_st = _FakeStreamlit()

    data_browser.render(fake_st, data_service=_FakeDataService())

    assert "Data Browser" in fake_st.titles
    assert fake_st.metrics == [
        ("Documents", 1),
        ("Chunks", 2),
        ("Images", 1),
    ]
    assert fake_st.dataframes[0][0]["source_name"] == "guide.pdf"
    assert "chunk-1 - alpha beta" in fake_st.expanders


class _FakeStreamlit:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self.messages: list[str] = []
        self.captions: list[str] = []
        self.metrics: list[tuple[str, int]] = []
        self.dataframes: list[list[dict]] = []
        self.expanders: list[str] = []

    def title(self, value: str) -> None:
        self.titles.append(value)

    def caption(self, value: str) -> None:
        self.captions.append(value)

    def info(self, value: str) -> None:
        self.messages.append(value)

    def error(self, value: str) -> None:
        self.messages.append(value)

    def selectbox(self, label: str, options):
        return list(options)[0]

    def text_input(self, label: str, value: str = "") -> str:
        return value

    def columns(self, count: int):
        return [_FakeColumn(self) for _ in range(count)]

    def metric(self, label: str, value) -> None:
        self.metrics.append((label, value))

    def subheader(self, value: str) -> None:
        self.titles.append(value)

    def dataframe(self, rows, **kwargs) -> None:
        self.dataframes.append(rows)

    def write(self, value: str) -> None:
        self.messages.append(value)

    def markdown(self, value: str) -> None:
        self.messages.append(value)

    def json(self, value) -> None:
        self.messages.append(str(value))

    def image(self, image_path, caption: str = "") -> None:
        self.messages.append(f"{caption}:{image_path}")

    def expander(self, label: str, expanded: bool = False):
        self.expanders.append(label)
        return _Context()

    def container(self, border: bool = False):
        return _Context()


class _FakeColumn:
    def __init__(self, parent: _FakeStreamlit) -> None:
        self.parent = parent

    def metric(self, label: str, value) -> None:
        self.parent.metric(label, value)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _FakeDataService:
    def list_collections(self):
        return ["docs"]

    def list_documents(self, collection=None, query: str = ""):
        return [
            {
                "doc_id": "doc-1",
                "source_path": "docs/guide.pdf",
                "source_name": "guide.pdf",
                "collection": "docs",
                "file_hash": "hash-1",
                "chunk_count": 2,
                "image_count": 1,
                "processed_at": "",
            }
        ]

    def collection_stats(self, collection=None):
        return {"document_count": 1, "chunk_count": 2, "image_count": 1}

    def get_document_detail(self, doc_id):
        return {
            "info": {
                "doc_id": "doc-1",
                "source_path": "docs/guide.pdf",
                "source_name": "guide.pdf",
                "file_hash": "hash-1",
            },
            "metadata": {"title": "Guide"},
            "chunks": [
                {
                    "id": "chunk-1",
                    "preview": "alpha beta",
                    "text": "alpha beta",
                    "metadata": {"source_path": "docs/guide.pdf"},
                }
            ],
            "images": [
                {
                    "image_id": "img-1",
                    "file_path": "missing.png",
                }
            ],
        }
