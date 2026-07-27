"""Dashboard evaluation panel page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from observability.dashboard.services.evaluation_service import EvaluationService


DEFAULT_TEST_SET = Path("tests/fixtures/golden_test_set.json")


def render(st, evaluation_service: EvaluationService | None = None) -> None:
    """Render golden test set execution and metric results."""
    service = evaluation_service or EvaluationService()
    st.title("Evaluation Panel")
    st.caption("Run golden test set evaluation and inspect aggregate metrics.")

    test_set_path = st.text_input("Golden test set path", str(DEFAULT_TEST_SET))
    top_k = _top_k_input(st)
    if not st.button("Run Evaluation"):
        st.info("Choose a golden test set, then click Run Evaluation.")
        return

    try:
        report = service.run_evaluation(
            test_set_path,
            top_k=top_k if top_k > 0 else None,
        )
    except Exception as exc:  # noqa: BLE001 - dashboard should surface readable errors.
        st.error(f"Evaluation failed: {exc}")
        return

    _render_report(st, report)


def _top_k_input(st) -> int:
    if hasattr(st, "number_input"):
        return int(
            st.number_input(
                "Override top_k (0 uses case/settings default)",
                min_value=0,
                value=0,
                step=1,
            )
        )
    value = st.text_input("Override top_k (0 uses case/settings default)", "0")
    return int(value or 0)


def _render_report(st, report: dict[str, Any]) -> None:
    metrics = dict(report.get("metrics", {}))
    case_results = list(report.get("case_results", []))
    details = dict(report.get("details", {}))

    st.subheader("Summary Metrics")
    if metrics:
        columns = st.columns(min(len(metrics), 4))
        for index, (name, value) in enumerate(metrics.items()):
            columns[index % len(columns)].metric(name, _format_metric(value))
    else:
        st.info("No metrics were returned by the evaluator.")

    st.write(f"Test set: `{details.get('test_set_path', '')}`")
    st.write(f"Cases: `{details.get('case_count', len(case_results))}`")

    if not case_results:
        st.info("No evaluation case results found.")
        return

    st.subheader("Case Results")
    rows = [_case_row(result) for result in case_results]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    labels = [f"{index + 1}. {result.get('query', '')}" for index, result in enumerate(case_results)]
    selected_label = st.selectbox("Case detail", labels)
    selected_result = case_results[labels.index(selected_label)]
    with st.expander(selected_label, expanded=True):
        st.json(selected_result)


def _case_row(result: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(result.get("metrics", {}))
    return {
        "query": result.get("query", ""),
        "retrieved_count": len(result.get("retrieved_ids", [])),
        "expected_count": len(result.get("expected_chunk_ids", [])),
        **{name: _format_metric(value) for name, value in metrics.items()},
    }


def _format_metric(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.4f}"
    return str(value)
