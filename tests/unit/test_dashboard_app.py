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

    data_browser.render(fake_st)
    ingestion_manager.render(fake_st)
    ingestion_traces.render(fake_st)
    query_traces.render(fake_st)
    evaluation_panel.render(fake_st)

    assert fake_st.titles == [
        "Data Browser",
        "Ingestion Manager",
        "Ingestion Traces",
        "Query Traces",
        "Evaluation Panel",
    ]
    assert len(fake_st.messages) == 5


class _FakeStreamlit:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self.messages: list[str] = []

    def title(self, value: str) -> None:
        self.titles.append(value)

    def info(self, value: str) -> None:
        self.messages.append(value)
