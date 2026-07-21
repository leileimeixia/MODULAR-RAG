"""Streamlit dashboard entrypoint."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from observability.dashboard.pages import (
    data_browser,
    evaluation_panel,
    ingestion_manager,
    ingestion_traces,
    overview,
    query_traces,
)


class DashboardError(RuntimeError):
    """Raised when the dashboard cannot be started."""


@dataclass(frozen=True)
class DashboardPage:
    title: str
    icon: str
    render: Callable


def page_specs() -> list[DashboardPage]:
    """Return the registered dashboard pages in navigation order."""
    return [
        DashboardPage("System Overview", ":material/home:", overview.render),
        DashboardPage("Data Browser", ":material/library_books:", data_browser.render),
        DashboardPage("Ingestion Manager", ":material/upload:", ingestion_manager.render),
        DashboardPage("Ingestion Traces", ":material/timeline:", ingestion_traces.render),
        DashboardPage("Query Traces", ":material/search:", query_traces.render),
        DashboardPage("Evaluation Panel", ":material/monitoring:", evaluation_panel.render),
    ]


def main() -> None:
    """Start the Streamlit dashboard."""
    st = _import_streamlit()
    st.set_page_config(
        page_title="Modular RAG Dashboard",
        page_icon=":material/psychology:",
        layout="wide",
    )
    pages = page_specs()
    if hasattr(st, "navigation") and hasattr(st, "Page"):
        streamlit_pages = [
            st.Page(lambda page=page: page.render(st), title=page.title, icon=page.icon)
            for page in pages
        ]
        st.navigation(streamlit_pages).run()
        return

    selected = st.sidebar.radio("Navigation", [page.title for page in pages])
    page = next(page for page in pages if page.title == selected)
    page.render(st)


def _import_streamlit():
    try:
        import streamlit as st  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DashboardError(
            "Streamlit is required to run the dashboard. "
            "Install project dependencies, then run `python scripts/start_dashboard.py`."
        ) from exc
    return st


if __name__ == "__main__":
    main()
