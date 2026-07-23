"""Dashboard ingestion traces page."""

from __future__ import annotations

from observability.dashboard.services.trace_service import TraceService


def render(st, trace_service: TraceService | None = None) -> None:
    """Render ingestion trace history and stage timing details."""
    service = trace_service or TraceService()
    st.title("Ingestion Traces")
    st.caption("Inspect ingestion history, stage timings, and per-stage details.")

    try:
        traces = service.list_ingestion_traces()
    except Exception as exc:  # noqa: BLE001 - dashboard should show readable errors.
        st.error(f"Failed to load ingestion traces: {exc}")
        return

    if not traces:
        st.info("No ingestion traces found yet.")
        return

    metric_columns = st.columns(3)
    metric_columns[0].metric("Traces", len(traces))
    metric_columns[1].metric("Completed", sum(trace["status"] == "completed" for trace in traces))
    metric_columns[2].metric("Failed", sum(trace["status"] == "failed" for trace in traces))

    st.subheader("Trace History")
    st.dataframe(traces, use_container_width=True, hide_index=True)

    labels = [
        f"{trace['started_at']} | {trace['status']} | {trace['trace_id']}"
        for trace in traces
    ]
    selected_label = st.selectbox("Trace detail", labels)
    selected_trace_id = traces[labels.index(selected_label)]["trace_id"]

    try:
        detail = service.get_ingestion_trace(selected_trace_id)
    except Exception as exc:  # noqa: BLE001 - keep history visible if one detail fails.
        st.error(f"Failed to load trace detail: {exc}")
        return

    _render_trace_detail(st, detail)


def _render_trace_detail(st, detail: dict) -> None:
    st.subheader(f"Trace {detail['trace_id']}")
    st.write(f"Status: `{detail['status']}`")
    st.write(f"Started: `{detail['started_at']}`")
    st.write(f"Finished: `{detail['finished_at']}`")
    st.write(f"Total elapsed: `{detail['total_elapsed_ms']} ms`")
    if detail.get("source_path"):
        st.write(f"Source: `{detail['source_path']}`")

    stage_rows = [
        {
            "stage": stage["name"],
            "method": stage["method"],
            "elapsed_ms": stage["elapsed_ms"],
            "failed": stage["failed"],
        }
        for stage in detail["stages"]
    ]
    st.subheader("Stage Timings")
    st.dataframe(stage_rows, use_container_width=True, hide_index=True)
    st.bar_chart(
        {row["stage"]: row["elapsed_ms"] for row in stage_rows},
        y_label="elapsed_ms",
    )

    st.subheader("Stage Details")
    for stage in detail["stages"]:
        with st.expander(f"{stage['index']}. {stage['name']} ({stage['elapsed_ms']} ms)", expanded=False):
            st.write(f"Method: `{stage['method']}`")
            st.json(stage["details"])
