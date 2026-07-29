# Company Knowledge Assistant

An AI-powered enterprise knowledge assistant that enables employees to ask questions about company documents using Retrieval-Augmented Generation (RAG).

The assistant now provides semantic ChromaDB retrieval, Gemini free-tier answer generation, and filename/page citations. Add `GEMINI_API_KEY` to `.env` to enable answers; document ingestion and embeddings remain local.

---

## Features

### Phase 2 (Current) — Document Ingestion

- Upload multiple PDF documents via Streamlit
- Automatic text extraction with PyPDFLoader
- Chunking with RecursiveCharacterTextSplitter (1000 / 200 overlap)
- Local Hugging Face embeddings (`BAAI/bge-small-en-v1.5`)
- Persistent ChromaDB vector storage
- Duplicate file detection
- Progress tracking and error handling

### Upcoming Phases

- Document retrieval and search
- RAG-powered Q&A chat interface
- Source citations with page numbers
- Authentication and cloud deployment

---

## Tech Stack

- Python
- Streamlit
- LangChain
- ChromaDB
- Hugging Face Embeddings (sentence-transformers)
- PyPDF

---

## Project Structure

```
company-knowledge-assistant/
├── app.py                  # Streamlit UI
├── backend/
│   ├── ingest.py           # Ingestion orchestration
│   ├── loaders.py          # PDF loading
│   ├── splitter.py         # Text chunking
│   ├── embeddings.py       # Hugging Face embeddings
│   ├── vectorstore.py      # ChromaDB operations
│   └── utils.py            # Paths and helpers
├── data/
│   ├── uploads/            # Saved PDF uploads
│   └── chroma_db/          # Persistent vector database
├── assets/
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

1. **Create a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/macOS
   venv\Scripts\activate           # Windows
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   On first run, the embedding model (`BAAI/bge-small-en-v1.5`) is downloaded automatically from Hugging Face.

3. **Configure environment (optional)**

   Copy `.env.example` to `.env` if you want a local env file for future settings. **No API key is required** for embeddings.

4. **Run the application**

   ```bash
   streamlit run app.py
   ```

---

## Usage

1. Open the app in your browser.
2. Select one or more PDF files using the file uploader.
3. Click **Process Documents**.
4. Monitor progress and review success/error messages in the UI.
5. Indexed documents and chunk counts appear in the sidebar.

Duplicate files (same filename already in `data/uploads` or already indexed) are skipped automatically.

---

## Project Status

Phase 2 complete — document ingestion pipeline is operational.
