"""Tests for LLM provider abstraction with mocked httpx."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.llm.provider import (
    ClaudeProvider,
    GroqProvider,
    LLMError,
    OllamaProvider,
    Provider,
    StubProvider,
    get_provider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(response_data: dict, status: int = 200) -> MagicMock:
    """Create a mock httpx.AsyncClient that returns a mock response from post()."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = response_data
    mock_resp.text = str(response_data)
    if status >= 400:
        from httpx import HTTPStatusError, Request, Response

        mock_resp.raise_for_status.side_effect = HTTPStatusError(
            f"HTTP {status}", request=Request("POST", "http://test"), response=Response(status)
        )
    else:
        mock_resp.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ===================================================================
# StubProvider
# ===================================================================


class TestStubProvider:
    async def test_returns_template(self):
        """Stub returns a JSON-encoded SBAR object (not labeled prose).

        The downstream parser in generate_escalation_note._parse_sbar
        expects JSON on the happy path; returning labeled prose dumped
        the entire string into the `situation` field. Keep this aligned
        with the JSON contract.
        """
        provider = StubProvider()
        result = await provider.complete("any prompt")
        data = json.loads(result)
        assert set(data.keys()) == {
            "situation",
            "background",
            "assessment",
            "recommendation",
        }
        assert all(isinstance(v, str) and v for v in data.values())
        # Field values must NOT carry the section-letter prefix —
        # the field name already serves as the section label.
        for letter in ("S:", "B:", "A:", "R:"):
            for value in data.values():
                assert not value.startswith(letter), (
                    f"Stub field value should not start with '{letter}': {value!r}"
                )

    async def test_name(self):
        assert StubProvider().name == "stub/template"

    async def test_implements_abc(self):
        assert isinstance(StubProvider(), Provider)


# ===================================================================
# OllamaProvider
# ===================================================================


class TestOllamaProvider:
    def test_default_config(self):
        provider = OllamaProvider()
        assert provider.name == "ollama/llama3.1"
        assert provider._base_url == "http://localhost:11434"

    def test_custom_config(self):
        env = {"OLLAMA_BASE_URL": "http://gpu:11434", "OLLAMA_MODEL": "phi3"}
        with patch.dict(os.environ, env):
            provider = OllamaProvider()
            assert provider.name == "ollama/phi3"
            assert provider._base_url == "http://gpu:11434"

    async def test_complete_success(self):
        provider = OllamaProvider()
        mock_client = _make_mock_client({"response": "Generated text here"})
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.complete("test prompt", max_tokens=100)
        assert result == "Generated text here"

    async def test_complete_error_raises(self):
        provider = OllamaProvider()
        mock_client = _make_mock_client({}, status=500)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LLMError) as exc_info:
                await provider.complete("test prompt")
            assert exc_info.value.provider == "ollama"


# ===================================================================
# GroqProvider
# ===================================================================


class TestGroqProvider:
    def test_requires_api_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
            with pytest.raises(LLMError) as exc_info:
                GroqProvider()
            assert "GROQ_API_KEY" in str(exc_info.value)

    def test_name(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = GroqProvider()
            assert provider.name == "groq/llama-3.1-70b-versatile"

    def test_custom_model(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "key", "GROQ_MODEL": "mixtral-8x7b"}):
            provider = GroqProvider()
            assert provider.name == "groq/mixtral-8x7b"

    async def test_complete_success(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = GroqProvider()
        resp_data = {"choices": [{"message": {"content": "Groq response"}}]}
        mock_client = _make_mock_client(resp_data)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.complete("test prompt")
        assert result == "Groq response"

    async def test_complete_error_raises(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = GroqProvider()
        mock_client = _make_mock_client({}, status=429)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LLMError) as exc_info:
                await provider.complete("test prompt")
            assert exc_info.value.provider == "groq"


# ===================================================================
# ClaudeProvider
# ===================================================================


class TestClaudeProvider:
    def test_requires_api_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            with pytest.raises(LLMError) as exc_info:
                ClaudeProvider()
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_name(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            provider = ClaudeProvider()
            assert provider.name == "claude/claude-sonnet-4-6"

    async def test_complete_success(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            provider = ClaudeProvider()
        resp_data = {"content": [{"type": "text", "text": "Claude response"}]}
        mock_client = _make_mock_client(resp_data)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.complete("test prompt")
        assert result == "Claude response"

    async def test_no_text_block_raises(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            provider = ClaudeProvider()
        resp_data = {"content": []}
        mock_client = _make_mock_client(resp_data)
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LLMError) as exc_info:
                await provider.complete("test prompt")
            assert "No text content" in str(exc_info.value)


# ===================================================================
# Factory
# ===================================================================


class TestGetProvider:
    def test_default_is_ollama(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = get_provider()
            assert isinstance(provider, OllamaProvider)

    def test_stub(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "stub"}):
            provider = get_provider()
            assert isinstance(provider, StubProvider)

    def test_groq_with_key(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test"}):
            provider = get_provider()
            assert isinstance(provider, GroqProvider)

    def test_groq_without_key_falls_back_to_ollama(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": ""}, clear=False):
            provider = get_provider()
            assert isinstance(provider, OllamaProvider)

    def test_claude_with_key(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "claude", "ANTHROPIC_API_KEY": "test"}):
            provider = get_provider()
            assert isinstance(provider, ClaudeProvider)

    def test_claude_without_key_falls_back_to_ollama(self):
        env = {"LLM_PROVIDER": "claude", "ANTHROPIC_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            provider = get_provider()
            assert isinstance(provider, OllamaProvider)

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "STUB"}):
            provider = get_provider()
            assert isinstance(provider, StubProvider)

    def test_unknown_falls_back_to_ollama(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "unknown_provider"}):
            provider = get_provider()
            assert isinstance(provider, OllamaProvider)
