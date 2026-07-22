"""Dashboard ingestion manager page."""

from __future__ import annotations

from observability.dashboard.services.ingestion_service import IngestionService


def render(st, ingestion_service: IngestionService | None = None) -> None:
    """Render upload, ingestion progress, and document deletion controls."""
    service = ingestion_service or IngestionService()
    st.title("Ingestion Manager")
    st.caption("Upload documents, run ingestion, watch progress, and delete indexed documents.")

    _render_upload(st, service)
    _render_delete_controls(st, service)


def _render_upload(st, service: IngestionService) -> None:
    st.subheader("Upload And Ingest")
    uploaded_file = st.file_uploader(
        "Choose a document",
        type=["pdf", "txt", "md", "docx"],
    )
    collection = st.text_input("Target collection", "default")
    force = st.checkbox("Force re-ingestion", value=False)
    progress_bar = st.progress(0)
    status = st.empty()

    if not st.button("Start Ingestion", disabled=uploaded_file is None):
        return

    def on_progress(stage: str, current: int, total: int) -> None:
        progress_bar.progress(current / total if total else 0)
        status.write(f"{stage}: {current}/{total}")

    try:
        result = service.ingest_upload(
            uploaded_file,
            collection=collection,
            force=force,
            on_progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001 - surface dashboard errors clearly.
        st.error(f"Ingestion failed: {exc}")
        return

    if result["skipped"]:
        st.info(f"Skipped unchanged document: `{result['file_path']}`")
    else:
        st.success(
            "Ingested `{file_path}`: chunks={chunk_count}, records={record_count}, images={image_count}".format(
                **result
            )
        )
    with st.expander("Progress events", expanded=False):
        st.json(result["progress_events"])


def _render_delete_controls(st, service: IngestionService) -> None:
    st.subheader("Manage Documents")
    collection_filter = st.text_input("Delete filter collection", "")
    try:
        documents = service.list_documents(collection=collection_filter.strip() or None)
    except Exception as exc:  # noqa: BLE001 - keep upload usable if listing fails.
        st.error(f"Failed to list documents: {exc}")
        return

    if not documents:
        st.info("No documents ingested yet.")
        return

    st.dataframe(documents, use_container_width=True, hide_index=True)
    labels = [
        f"{document['source_name']} | chunks={document['chunk_count']} | {document['source_path']}"
        for document in documents
    ]
    selected_label = st.selectbox("Document to delete", labels)
    selected_document = documents[labels.index(selected_label)]

    if not st.button("Delete Selected Document"):
        return

    try:
        result = service.delete_document(
            selected_document["source_path"],
            collection=selected_document.get("collection") or None,
        )
    except Exception as exc:  # noqa: BLE001 - surface dashboard errors clearly.
        st.error(f"Delete failed: {exc}")
        return
    st.success(
        "Deleted vectors={vector_deleted}, bm25={bm25_deleted}, images={images_deleted}, integrity={integrity_deleted}".format(
            **result
        )
    )
