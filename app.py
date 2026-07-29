"""Streamlit UI for document ingestion and RAG-powered company Q&A."""

from __future__ import annotations

import streamlit as st

from backend.embeddings import EmbeddingConfigError, get_embeddings
from backend.ingest import check_configuration, ingest_uploaded_files, validate_pipeline_ready
from backend.rag import AnswerGenerationError, answer_question
from backend.utils import ensure_directories, list_uploaded_files
from backend.vectorstore import get_indexed_document_count, get_indexed_sources, get_vectorstore

st.set_page_config(page_title="Company Knowledge Assistant", page_icon="📚", layout="wide")
ensure_directories()


@st.cache_resource(show_spinner=False)
def get_cached_vectorstore():
    """Avoid rebuilding the embedding client for every Streamlit rerun."""
    return get_vectorstore(get_embeddings())


def indexed_status() -> tuple[int, list[str]]:
    """Read index statistics without breaking the UI when local services fail."""
    try:
        vectorstore = get_cached_vectorstore()
        return get_indexed_document_count(vectorstore), sorted(get_indexed_sources(vectorstore))
    except Exception:
        return 0, []


def render_sidebar() -> None:
    st.sidebar.title("📚 Knowledge Base")
    st.sidebar.caption("Upload company PDFs, then ask grounded questions about them.")
    st.sidebar.divider()
    st.sidebar.subheader("Pipeline Status")
    validation_error = check_configuration()
    if validation_error:
        st.sidebar.error(validation_error)
    else:
        st.sidebar.success("Ingestion pipeline ready")
    chunk_count, indexed_sources = indexed_status()
    st.sidebar.metric("Indexed chunks", chunk_count)
    st.sidebar.metric("Indexed documents", len(indexed_sources))
    st.sidebar.metric("Saved uploads", len(list_uploaded_files()))
    if indexed_sources:
        st.sidebar.subheader("Indexed Files")
        for name in indexed_sources:
            st.sidebar.caption(f"• {name}")


def render_ingestion() -> None:
    """Render the established upload-to-Chroma ingestion experience."""
    st.subheader("Add company documents")
    st.write("Upload PDF documents to chunk, embed, and store in the company knowledge base.")
    uploaded_files = st.file_uploader("Choose PDF files", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        st.info(f"{len(uploaded_files)} file(s) selected.")
        with st.expander("Selected files"):
            for uploaded in uploaded_files:
                st.write(f"• {uploaded.name} ({uploaded.size:,} bytes)")
    if st.button("Process Documents", type="primary", disabled=not uploaded_files):
        validation_error = validate_pipeline_ready()
        if validation_error:
            st.error(validation_error)
            return
        progress_bar = st.progress(0, text="Starting ingestion...")
        status = st.empty()
        file_payloads = [(uploaded.name, uploaded.getvalue()) for uploaded in uploaded_files or []]
        def update_progress(current: int, total: int, filename: str) -> None:
            progress_bar.progress(current / total, text=f"Processing {current}/{total}: {filename}")
            status.info(f"Processing **{filename}** ({current} of {total})…")
        results = ingest_uploaded_files(file_payloads, progress_callback=update_progress)
        progress_bar.progress(1.0, text="Ingestion complete.")
        status.empty()
        get_cached_vectorstore.clear()
        success_count = sum(result.success for result in results)
        skipped_count = sum(result.skipped for result in results)
        failed_count = len(results) - success_count - skipped_count
        if success_count:
            st.success(f"Successfully processed {success_count} file(s).")
        if skipped_count:
            st.warning(f"Skipped {skipped_count} duplicate file(s).")
        if failed_count:
            st.error(f"Failed to process {failed_count} file(s).")
        for result in results:
            if result.success:
                st.success(f"**{result.filename}** — {result.message} ({result.chunks_count} chunks)")
            elif result.skipped:
                st.warning(f"**{result.filename}** — {result.message}")
            else:
                st.error(f"**{result.filename}** — {result.message}")


def render_sources(sources) -> None:
    if not sources:
        return
    st.markdown("#### Sources")
    seen: set[tuple[str, int | None]] = set()
    for source in sources:
        key = (source.filename, source.page_number)
        if key in seen:
            continue
        seen.add(key)
        page = f", page {source.page_number}" if source.page_number is not None else ""
        with st.expander(f"{source.filename}{page} · relevance {source.score:.0%}"):
            st.write(source.excerpt)


def render_qa() -> None:
    st.subheader("Ask the knowledge base")
    st.write("Answers are generated from the most relevant indexed document chunks.")
    chunk_count, _ = indexed_status()
    if not chunk_count:
        st.info("No indexed documents yet. Upload and process a PDF to begin asking questions.")
        return
    for message in st.session_state.get("messages", []):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                render_sources(message.get("sources", []))
    question = st.chat_input("Ask a question about your company documents")
    if not question:
        return
    st.session_state.setdefault("messages", []).append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Searching documents and drafting an answer…"):
            try:
                result = answer_question(question)
            except AnswerGenerationError as exc:
                st.error(str(exc))
                return
            st.markdown(result.text)
            render_sources(result.sources)
    st.session_state["messages"].append({"role": "assistant", "content": result.text, "sources": result.sources})


def main() -> None:
    render_sidebar()
    st.title("Company Knowledge Assistant")
    st.caption("A private, PDF-backed RAG workspace for company knowledge.")
    chat_tab, upload_tab = st.tabs(["💬 Ask questions", "📄 Upload documents"])
    with chat_tab:
        render_qa()
    with upload_tab:
        render_ingestion()


if __name__ == "__main__":
    main()
