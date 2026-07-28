"""Streamlit application for the Company Knowledge Assistant — Phase 2: Document Ingestion."""

from __future__ import annotations

import streamlit as st

from backend.embeddings import EmbeddingConfigError, get_embeddings
from backend.ingest import check_configuration, ingest_uploaded_files, validate_pipeline_ready
from backend.utils import ensure_directories, list_uploaded_files
from backend.vectorstore import get_indexed_document_count, get_indexed_sources, get_vectorstore

st.set_page_config(
    page_title="Company Knowledge Assistant",
    page_icon="📚",
    layout="wide",
)

ensure_directories()


def render_sidebar() -> None:
    """Render sidebar with pipeline status and indexed document info."""
    st.sidebar.title("Document Ingestion")
    st.sidebar.markdown(
        """
        Upload company PDF documents to build a searchable knowledge base.

        **Phase 2** — Ingestion only. Chat and Q&A coming in a later phase.
        """
    )

    st.sidebar.divider()
    st.sidebar.subheader("Pipeline Status")

    validation_error = check_configuration()
    if validation_error:
        st.sidebar.error(validation_error)
    else:
        st.sidebar.success("Pipeline ready")

    try:
        vectorstore = get_vectorstore(get_embeddings())
        chunk_count = get_indexed_document_count(vectorstore)
        indexed_sources = sorted(get_indexed_sources(vectorstore))
    except EmbeddingConfigError:
        chunk_count = 0
        indexed_sources = []
    except Exception:
        chunk_count = 0
        indexed_sources = []

    st.sidebar.metric("Indexed Chunks", chunk_count)
    st.sidebar.metric("Indexed Documents", len(indexed_sources))

    uploaded_files = list_uploaded_files()
    st.sidebar.metric("Saved Uploads", len(uploaded_files))

    if indexed_sources:
        st.sidebar.subheader("Indexed Files")
        for name in indexed_sources:
            st.sidebar.caption(f"• {name}")

    if uploaded_files:
        st.sidebar.subheader("Uploaded Files")
        for name in uploaded_files:
            st.sidebar.caption(f"• {name}")


def render_main() -> None:
    """Render the main upload and processing interface."""
    st.title("📚 Company Knowledge Assistant")
    st.markdown(
        """
        Upload one or more **PDF documents** to ingest them into the company knowledge base.
        Files are chunked, embedded, and stored in a persistent vector database.
        """
    )

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        help="Select one or more PDF files to process.",
    )

    if uploaded_files:
        st.info(f"{len(uploaded_files)} file(s) selected.")
        with st.expander("Selected files"):
            for uploaded in uploaded_files:
                st.write(f"• {uploaded.name} ({uploaded.size:,} bytes)")

    process_clicked = st.button(
        "Process Documents",
        type="primary",
        disabled=not uploaded_files,
    )

    if process_clicked and uploaded_files:
        validation_error = validate_pipeline_ready()
        if validation_error:
            st.error(validation_error)
            return

        progress_bar = st.progress(0, text="Starting ingestion...")
        status_placeholder = st.empty()
        results_container = st.container()

        file_payloads = [(uploaded.name, uploaded.getvalue()) for uploaded in uploaded_files]
        total = len(file_payloads)

        def update_progress(current: int, total_files: int, filename: str) -> None:
            progress_bar.progress(
                current / total_files,
                text=f"Processing {current}/{total_files}: {filename}",
            )
            status_placeholder.info(f"Processing **{filename}** ({current} of {total_files})...")

        results = ingest_uploaded_files(file_payloads, progress_callback=update_progress)

        progress_bar.progress(1.0, text="Ingestion complete.")
        status_placeholder.empty()

        success_count = sum(1 for result in results if result.success)
        skipped_count = sum(1 for result in results if result.skipped)
        failure_count = len(results) - success_count - skipped_count

        if success_count:
            st.success(f"Successfully processed {success_count} file(s).")
        if skipped_count:
            st.warning(f"Skipped {skipped_count} duplicate file(s).")
        if failure_count:
            st.error(f"Failed to process {failure_count} file(s).")

        with results_container:
            st.subheader("Processing Results")
            for result in results:
                if result.success:
                    st.success(f"**{result.filename}** — {result.message} ({result.chunks_count} chunks)")
                elif result.skipped:
                    st.warning(f"**{result.filename}** — {result.message}")
                else:
                    st.error(f"**{result.filename}** — {result.message}")


def main() -> None:
    """Application entry point."""
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
