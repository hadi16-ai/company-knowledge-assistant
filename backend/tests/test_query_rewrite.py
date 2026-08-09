"""Unit tests for conversational query rewriting (the Gemini client is mocked out —
no live API calls in tests, matching the rag.py/reranker test conventions)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.rag.query_rewrite import QueryRewriteError, rewrite_query
from app.rag.rag import ConversationTurn


def _mock_response(text: str):
    return SimpleNamespace(text=text)


def test_rewrite_skips_model_call_when_no_history():
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        result = rewrite_query("What is the leave policy?", [])

    mock_get_client.assert_not_called()
    assert result == "What is the leave policy?"


def test_rewrite_skips_when_history_has_no_user_turns():
    history = [ConversationTurn(role="assistant", content="Hello, how can I help?")]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        result = rewrite_query("What is the leave policy?", history)

    mock_get_client.assert_not_called()
    assert result == "What is the leave policy?"


def test_rewrite_resolves_follow_up_using_history():
    history = [
        ConversationTurn(role="user", content="What is the leave policy?"),
        ConversationTurn(role="assistant", content="Employees get 20 days of annual leave."),
    ]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.return_value = _mock_response(
            "What was the leave policy last year?"
        )
        result = rewrite_query("What about last year?", history)

    assert result == "What was the leave policy last year?"


def test_rewrite_resolves_ambiguous_pronoun_using_full_history():
    history = [
        ConversationTurn(role="user", content="Tell me about the expense reimbursement policy."),
        ConversationTurn(role="assistant", content="Expenses must be submitted within 30 days with receipts."),
        ConversationTurn(role="user", content="And the travel policy?"),
        ConversationTurn(role="assistant", content="Travel must be pre-approved by a manager."),
    ]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.return_value = _mock_response(
            "What is required to get travel pre-approved by a manager?"
        )
        result = rewrite_query("What do I need for that?", history)

    assert "travel" in result.lower()


def test_rewrite_standalone_query_returned_unchanged_by_model():
    """Model is instructed to return already-self-contained questions as-is."""
    history = [ConversationTurn(role="user", content="What is the leave policy?")]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.return_value = _mock_response(
            "What is the expense reimbursement policy?"
        )
        result = rewrite_query("What is the expense reimbursement policy?", history)

    assert result == "What is the expense reimbursement policy?"


def test_rewrite_falls_back_to_original_when_client_unavailable():
    history = [ConversationTurn(role="user", content="What is the leave policy?")]
    with patch("app.rag.query_rewrite._get_client", side_effect=QueryRewriteError("no api key")):
        result = rewrite_query("What about last year?", history)

    assert result == "What about last year?"


def test_rewrite_falls_back_to_original_when_generation_raises():
    history = [ConversationTurn(role="user", content="What is the leave policy?")]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.side_effect = RuntimeError("network error")
        result = rewrite_query("What about last year?", history)

    assert result == "What about last year?"


def test_rewrite_falls_back_to_original_on_empty_model_output():
    history = [ConversationTurn(role="user", content="What is the leave policy?")]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.return_value = _mock_response("")
        result = rewrite_query("What about last year?", history)

    assert result == "What about last year?"


def test_rewrite_falls_back_to_original_on_oversized_output():
    history = [ConversationTurn(role="user", content="What is the leave policy?")]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.return_value = _mock_response("x" * 501)
        result = rewrite_query("What about last year?", history)

    assert result == "What about last year?"


def test_rewrite_strips_surrounding_quotes():
    history = [ConversationTurn(role="user", content="What is the leave policy?")]
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        mock_get_client.return_value.models.generate_content.return_value = _mock_response(
            '"What was the leave policy last year?"'
        )
        result = rewrite_query("What about last year?", history)

    assert result == "What was the leave policy last year?"


def test_rewrite_blank_question_returned_unchanged():
    with patch("app.rag.query_rewrite._get_client") as mock_get_client:
        result = rewrite_query("   ", [ConversationTurn(role="user", content="hi")])

    mock_get_client.assert_not_called()
    assert result == "   "
