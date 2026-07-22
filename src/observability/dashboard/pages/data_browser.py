"""Dashboard data browser page."""

from __future__ import annotations

from pathlib import Path

from observability.dashboard.services.data_service import DataService


def render(st, data_service: DataService | None = None) -> None:
    """Render indexed documents, chunks, metadata, and image references."""
    service = data_service or DataService()
    st.title("Data Browser")
    st.caption("Browse ingested documents, chunk text, metadata, and image references.")

    try:
        collections = service.list_collections()
        collection_options = ["All", *collections]
        selected_collection = st.selectbox("Collection", collection_options)
        collection = None if selected_collection == "All" else selected_collection
        query = st.text_input("Search documents", "")
        documents = service.list_documents(collection=collection, query=query)
        stats = service.collection_stats(collection=collection)
    except Exception as exc:  # noqa: BLE001 - dashboard should show readable errors.
        st.error(f"Failed to load indexed documents: {exc}")
        return

    metric_columns = st.columns(3)
    metric_columns[0].metric("Documents", stats.get("document_count", 0))
    metric_columns[1].metric("Chunks", stats.get("chunk_count", 0))
    metric_columns[2].metric("Images", stats.get("image_count", 0))

    if not documents:
        st.info("No indexed documents found for the current filters.")
        return

    st.subheader("Documents")
    st.dataframe(documents, use_container_width=True, hide_index=True)

    document_labels = [
        f"{document['source_name']} | chunks={document['chunk_count']} | {document['source_path']}"
        for document in documents
    ]
    selected_label = st.selectbox("Document detail", document_labels)
    selected_index = document_labels.index(selected_label)
    selected_document = documents[selected_index]

    try:
        detail = service.get_document_detail(selected_document["source_path"])
    except Exception as exc:  # noqa: BLE001 - keep page usable for partial data issues.
        st.error(f"Failed to load document detail: {exc}")
        return

    _render_document_detail(st, detail)


def _render_document_detail(st, detail: dict) -> None:
    info = detail["info"]
    st.subheader(info["source_name"])
    st.write(f"Source: `{info['source_path']}`")
    st.write(f"Document id: `{info['doc_id']}`")
    if info.get("file_hash"):
        st.write(f"File hash: `{info['file_hash']}`")

    with st.expander("Document metadata", expanded=False):
        st.json(detail["metadata"])

    st.subheader("Chunks")
    for chunk in detail["chunks"]:
        with st.expander(f"{chunk['id']} - {chunk['preview']}", expanded=False):
            st.markdown(chunk["text"])
            st.json(chunk["metadata"])

    st.subheader("Images")
    if not detail["images"]:
        st.info("No images are associated with this document.")
        return
    for image in detail["images"]:
        image_path = str(image.get("file_path", ""))
        with st.container(border=True):
            st.write(f"Image id: `{image.get('image_id', '')}`")
            st.write(f"Path: `{image_path}`")
            if image_path and Path(image_path).is_file():
                st.image(image_path, caption=image.get("image_id", ""))
