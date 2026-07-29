"""Streamlit UI for document ingestion and RAG-powered company Q&A."""

from __future__ import annotations

import os
from pathlib import PureWindowsPath

import streamlit as st

from backend.embeddings import EMBEDDING_MODEL, EmbeddingConfigError, get_embeddings
from backend.ingest import check_configuration, ingest_uploaded_files, validate_pipeline_ready
from backend.rag import DEFAULT_GEMINI_MODEL, AnswerGenerationError, answer_question
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


def display_filename(source: str) -> str:
    """Return a presentation-safe filename for a document source."""
    return PureWindowsPath(source).name or "Unknown document"


def render_sidebar() -> None:
    st.sidebar.title("📚 Knowledge Base")
    st.sidebar.caption("Upload company PDFs, then ask grounded questions about them.")
    st.sidebar.divider()
    chunk_count, indexed_sources = indexed_status()
    if indexed_sources:
        st.sidebar.subheader("Indexed Files")
        for name in indexed_sources:
            st.sidebar.caption(f"• {display_filename(name)}")
    st.sidebar.divider()
    st.sidebar.subheader("💬 Conversation")
    st.sidebar.success("● Current session")
    questions = [message["content"] for message in st.session_state.get("messages", []) if message["role"] == "user"]
    if questions:
        for index, question in enumerate(questions, start=1):
            st.sidebar.caption(f"{index}. {question}")
    else:
        st.sidebar.caption("No questions in this session yet.")
    if st.sidebar.button("🗑 Clear Conversation", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()
    with st.sidebar.expander("Developer Diagnostics", expanded=False):
        validation_error = check_configuration()
        if validation_error:
            st.error(validation_error)
        else:
            st.success("Pipeline ready")
        st.metric("Documents", len(indexed_sources))
        st.metric("Chunks", chunk_count)
        st.metric("Uploads", len(list_uploaded_files()))
        st.caption(f"**Embedding Model**  \n{EMBEDDING_MODEL}")
        st.caption(f"**Gemini Model**  \n{os.getenv('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)}")
        st.caption("**Vector Store**  \nChromaDB (local persistent store)")


def render_ingestion() -> None:
    """Render the established upload-to-Chroma ingestion experience."""
    st.subheader("Add company documents")
    st.write("Upload PDF documents to chunk, embed, and store in the company knowledge base.")
    uploaded_files = st.file_uploader("Choose PDF files", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        st.info(f"{len(uploaded_files)} file(s) selected.")
        with st.expander("Selected files"):
            for uploaded in uploaded_files:
                st.write(f"• {display_filename(uploaded.name)} ({uploaded.size:,} bytes)")
    else:
        st.info("No PDFs selected yet. Add a company document to build your knowledge base.")
    if st.button("Process Documents", type="primary", disabled=not uploaded_files):
        validation_error = validate_pipeline_ready()
        if validation_error:
            st.error(validation_error)
            return
        progress_bar = st.progress(0, text="Starting ingestion...")
        status = st.empty()
        file_payloads = [(uploaded.name, uploaded.getvalue()) for uploaded in uploaded_files or []]
        def update_progress(current: int, total: int, filename: str) -> None:
            display_name = display_filename(filename)
            progress_bar.progress(current / total, text=f"Processing {current}/{total}: {display_name}")
            status.info(f"Processing **{display_name}** ({current} of {total})…")
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
            display_name = display_filename(result.filename)
            if result.success:
                st.success(f"**{display_name}** — {result.message} ({result.chunks_count} chunks)")
            elif result.skipped:
                st.warning(f"**{display_name}** — {result.message}")
            else:
                st.error(f"**{display_name}** — {result.message}")


def render_sources(sources) -> None:
    """Render retrieved citations as one expandable card per document."""
    if not sources:
        st.info("No relevant context was found in the indexed documents for this question.")
        return
    st.markdown("#### 📚 Sources")
    grouped_sources: dict[str, dict[int | None, float]] = {}
    for source in sources:
        filename = display_filename(source.filename)
        pages = grouped_sources.setdefault(filename, {})
        pages[source.page_number] = max(pages.get(source.page_number, 0.0), source.score)
    for filename, pages in grouped_sources.items():
        with st.expander(f"📄 {filename}"):
            st.caption("Referenced Pages")
            for page_number, score in pages.items():
                page_label = f"Page {page_number}" if page_number is not None else "Page unavailable"
                st.markdown(f"• {page_label} ({score:.0%})")


def render_answer(text: str, sources) -> None:
    """Render a generated response in a distinct answer card with citations."""
    with st.container(border=True):
        st.markdown("### 🤖 AI Answer")
        st.markdown(text)
        st.divider()
        render_sources(sources)


def render_user_question(question: str) -> None:
    """Render a user prompt as a chronological conversation step."""
    st.markdown("#### 👤 User Question")
    st.markdown(question)


def render_qa() -> None:
    st.subheader("Ask the knowledge base")
    st.write("Answers are generated from the most relevant indexed document chunks.")
    chunk_count, _ = indexed_status()
    if not chunk_count:
        st.info("No PDFs are ready yet. Upload and process a document before asking a question.")
        return
    messages = st.session_state.get("messages", [])
    for message in messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_answer(message["content"], message.get("sources", []))
            else:
                render_user_question(message["content"])
    if not messages:
        st.info("Ask a question to search your company knowledge base and receive a grounded answer.")
    question = st.chat_input("Ask a question about your company documents")
    if not question:
        return
    st.session_state.setdefault("messages", []).append({"role": "user", "content": question})
    with st.chat_message("user"):
        render_user_question(question)
    with st.chat_message("assistant"):
        with st.status("🔍 Searching documents...", expanded=True) as status:
            st.write("🔍 Searching documents...")
            st.write("📚 Retrieving context...")
            status.update(label="🤖 Generating answer...", state="running")
            try:
                result = answer_question(question)
            except AnswerGenerationError as exc:
                status.update(label="Unable to generate an answer", state="error")
                st.error(str(exc))
                return
            status.update(label="Answer generated", state="complete", expanded=False)
        render_answer(result.text, result.sources)
        st.success("✓ Grounded answer generated from retrieved documents.")
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
