"""Dashboard query traces page."""

from __future__ import annotations

from observability.dashboard.services.trace_service import TraceService


def render(st, trace_service: TraceService | None = None) -> None:
    """Render query trace history and retrieval/rerank details."""
    service = trace_service or TraceService()
    st.title("Query Traces")
    st.caption("Inspect query history, dense/sparse retrieval, fusion, and rerank details.")

    try:
        traces = service.list_query_traces()
    except Exception as exc:  # noqa: BLE001 - dashboard should show readable errors.
        st.error(f"Failed to load query traces: {exc}")
        return

    if not traces:
        st.info("No query traces found yet.")
        return

    metric_columns = st.columns(3)
    metric_columns[0].metric("Queries", len(traces))
    metric_columns[1].metric("Completed", sum(trace["status"] == "completed" for trace in traces))
    metric_columns[2].metric("Failed", sum(trace["status"] == "failed" for trace in traces))

    query_filter = st.text_input("Search trace history", "")
    filtered = _filter_traces(traces, query_filter)
    if not filtered:
        st.info("No query traces match the current filter.")
        return

    st.subheader("Query History")
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    labels = [
        f"{trace['started_at']} | {trace['status']} | {trace['trace_id']}"
        for trace in filtered
    ]
    selected_label = st.selectbox("Trace detail", labels)
    selected_trace_id = filtered[labels.index(selected_label)]["trace_id"]

    try:
        detail = service.get_query_trace(selected_trace_id)
    except Exception as exc:  # noqa: BLE001 - keep history visible if one detail fails.
        st.error(f"Failed to load query trace detail: {exc}")
        return

    _render_query_detail(st, detail)


def _render_query_detail(st, detail: dict) -> None:
    st.subheader(f"Trace {detail['trace_id']}")
    st.write(f"Status: `{detail['status']}`")
    st.write(f"Started: `{detail['started_at']}`")
    st.write(f"Finished: `{detail['finished_at']}`")
    st.write(f"Total elapsed: `{detail['total_elapsed_ms']} ms`")

    st.subheader("Dense / Sparse / Fusion")
    comparison = detail.get("retrieval_comparison", [])
    if comparison:
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        st.bar_chart(
            {row["route"]: row["result_count"] for row in comparison},
            y_label="result_count",
        )
    else:
        st.info("No retrieval comparison stages were recorded.")

    st.subheader("Rerank")
    rerank = detail.get("rerank_summary", {})
    if rerank:
        st.json(rerank)
    else:
        st.info("No rerank stage was recorded.")

    st.subheader("Stage Details")
    for stage in detail["stages"]:
        with st.expander(f"{stage['index']}. {stage['name']} ({stage['elapsed_ms']} ms)", expanded=False):
            st.write(f"Method: `{stage['method']}`")
            st.json(stage["details"])


def _filter_traces(traces: list[dict], query: str) -> list[dict]:
    query = query.strip().lower()
    if not query:
        return traces
    return [
        trace
        for trace in traces
        if query in " ".join(
            str(trace.get(key, ""))
            for key in ["trace_id", "query", "started_at", "status"]
        ).lower()
    ]
