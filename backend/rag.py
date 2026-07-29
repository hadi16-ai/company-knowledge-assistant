"""Gemini answer generation for the Company Knowledge Assistant."""

from __future__ import annotations

import os
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass

from backend.context import SourceCitation, build_context
from backend.retrieval import DEFAULT_RETRIEVAL_K, RetrievalError, retrieve_documents
from backend.utils import load_environment

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


class AnswerGenerationError(Exception):
    """Raised when a grounded answer cannot be generated."""


@dataclass(frozen=True)
class RAGAnswer:
    """A generated answer and its supporting retrieved sources."""

    text: str
    sources: list[SourceCitation]


def _get_gemini_configuration() -> tuple[str, str]:
    """Load the free-tier-compatible Gemini API configuration."""
    load_environment()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AnswerGenerationError(
            "GEMINI_API_KEY is not configured. Add it to .env to enable answers."
        )
    return api_key, os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def _extract_response_text(payload: dict) -> str:
    """Extract text from the Gemini generateContent REST response."""
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(str(part.get("text", "")) for part in parts).strip()


def answer_question(question: str, k: int = DEFAULT_RETRIEVAL_K) -> RAGAnswer:
    """Retrieve relevant chunks and generate an answer grounded only in them."""
    try:
        matches = retrieve_documents(question, k=k)
    except RetrievalError as exc:
        raise AnswerGenerationError(str(exc)) from exc

    if not matches:
        raise AnswerGenerationError(
            "No relevant indexed content was found. Upload and process company PDFs first."
        )

    context, sources = build_context(matches)

    if not context:
        raise AnswerGenerationError(
            "The retrieved documents did not contain readable text."
        )

    api_key, model = _get_gemini_configuration()

    instructions = (
        "You are the Company Knowledge Assistant. "
        "Answer only from the supplied company-document context. "
        "If the context does not answer the question, say that clearly. "
        "Do not invent facts or cite sources not provided. "
        "Keep the answer concise and use source labels such as [Source 1] when helpful."
    )

    prompt = (
        f"Question:\n{question.strip()}\n\n"
        f"Company-document context:\n{context}"
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": instructions}]
        },
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 800,
        },
    }

    url = (
        f"https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    print("\n>>> About to call Gemini API...\n")

    try:
        with urlopen(request, timeout=45) as response:
            response_body = response.read().decode("utf-8")
            print("\n========== GEMINI SUCCESS ==========")
            print(response_body)
            print("====================================\n")

            answer = _extract_response_text(json.loads(response_body))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")

        print("\n========== GEMINI HTTP ERROR ==========")
        print(f"Status Code: {exc.code}")
        print(error_body)
        print("=======================================\n")

        raise AnswerGenerationError(
            f"HTTP {exc.code}: {error_body}"
        ) from exc

    except URLError as exc:
        print("\n========== GEMINI URL ERROR ==========")
        print(exc)
        print("======================================\n")

        raise AnswerGenerationError(
            f"Network error: {exc}"
        ) from exc

    except Exception as exc:
        print("\n========== GEMINI UNKNOWN ERROR ==========")
        print(repr(exc))
        print("==========================================\n")

        raise AnswerGenerationError(str(exc)) from exc

    if not answer:
        raise AnswerGenerationError(
            "Gemini returned an empty answer."
        )

    return RAGAnswer(text=answer, sources=sources)