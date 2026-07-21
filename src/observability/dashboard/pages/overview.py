"""System overview page for the Streamlit dashboard."""

from __future__ import annotations

from observability.dashboard.services.config_service import ConfigService


def render(st, config_service: ConfigService | None = None) -> None:
    """Render current component configuration and data statistics."""
    service = config_service or ConfigService()
    st.title("System Overview")
    st.caption("Current pluggable component configuration and local data status.")

    try:
        overview = service.overview()
    except Exception as exc:  # noqa: BLE001 - dashboard should display readable errors.
        st.error(f"Failed to load dashboard overview: {exc}")
        return

    stats = overview["data_stats"]
    metric_columns = st.columns(4)
    metric_columns[0].metric("Vector Records", stats.get("record_count", 0))
    metric_columns[1].metric("Source Documents", stats.get("source_count", 0))
    metric_columns[2].metric("Collection", stats.get("collection_name", "unknown"))
    metric_columns[3].metric("Data Status", stats.get("status", "unknown"))

    if stats.get("error"):
        st.warning(stats["error"])

    st.subheader("Component Configuration")
    for card in overview["components"]:
        with st.container(border=True):
            st.markdown(f"**{card['name']}**")
            left, right, status = st.columns(3)
            left.write(f"Provider: `{card['provider']}`")
            right.write(f"Model: `{card['model']}`")
            status.write(f"Status: `{card['status']}`")
            st.json(card["details"])

    st.subheader("Storage")
    st.write(f"Settings: `{overview['settings_path']}`")
    st.write(f"Persist directory: `{stats.get('persist_directory', '')}`")
    st.write(f"Collection file: `{stats.get('collection_file', '')}`")
