"""Shared utilities for paths, configuration, and file management."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Project root is one level above the backend package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "company_documents"


def load_environment() -> None:
    """Load environment variables from the project .env file."""
    load_dotenv(PROJECT_ROOT / ".env")


def ensure_directories() -> None:
    """Create required data directories if they do not exist."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def is_duplicate_upload(filename: str) -> bool:
    """Return True if a file with the same name already exists in uploads."""
    return (UPLOADS_DIR / filename).exists()


def save_uploaded_file(filename: str, file_bytes: bytes) -> Path:
    """
    Save uploaded file bytes to the uploads directory.

    Args:
        filename: Original filename of the uploaded file.
        file_bytes: Raw file content.

    Returns:
        Path to the saved file.
    """
    ensure_directories()
    destination = UPLOADS_DIR / filename
    destination.write_bytes(file_bytes)
    return destination


def list_uploaded_files() -> list[str]:
    """Return sorted list of filenames currently in the uploads directory."""
    ensure_directories()
    return sorted(
        path.name for path in UPLOADS_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"
    )
