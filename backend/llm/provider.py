"""LLM provider abstraction layer.

Provider ABC with implementations for Ollama, Groq, Claude, and a Stub
(for CI). Factory function selects provider via LLM_PROVIDER env var.

API keys come from env vars (GROQ_API_KEY, ANTHROPIC_API_KEY), NEVER from
HTTP headers. SHARP headers are for FHIR context only.

Reference: BUILD_PLAN F5, PROJECT_BRIEF:56
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import httpx


class LLMError(Exception):
    """Raised when an LLM provider call fails."""

    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider


class Provider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name, e.g. 'ollama/llama3.1'."""
        ...

    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate a completion for the given prompt.

        Args:
            prompt: The input prompt text.
            max_tokens: Maximum tokens to generate.

        Returns:
            Generated text string.

        Raises:
            LLMError: On any provider failure.
        """
        ...


class OllamaProvider(Provider):
    """Ollama REST API provider (local inference).

    Env vars:
        OLLAMA_BASE_URL: Ollama server URL (default http://localhost:11434)
        OLLAMA_MODEL: Model name (default llama3.1)
    """

    def __init__(self) -> None:
        self._base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self._model = os.environ.get("OLLAMA_MODEL", "llama3.1")

    @property
    def name(self) -> str:
        return f"ollama/{self._model}"

    async def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": max_tokens},
                    },
                )
                resp.raise_for_status()
                return resp.json()["response"]
        except (httpx.HTTPError, KeyError) as e:
            raise LLMError("ollama", str(e)) from e


class GroqProvider(Provider):
    """Groq API provider via httpx (no SDK dependency).

    Env vars:
        GROQ_API_KEY: Required API key.
        GROQ_MODEL: Model name (default llama-3.1-70b-versatile)
    """

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        self._api_key = os.environ.get("GROQ_API_KEY", "")
        self._model = os.environ.get("GROQ_MODEL", "llama-3.1-70b-versatile")
        if not self._api_key:
            raise LLMError("groq", "GROQ_API_KEY env var is required")

    @property
    def name(self) -> str:
        return f"groq/{self._model}"

    async def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                resp = await client.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as e:
            raise LLMError("groq", str(e)) from e


class ClaudeProvider(Provider):
    """Anthropic Messages API provider via httpx (no SDK dependency).

    Env vars:
        ANTHROPIC_API_KEY: Required API key.
        ANTHROPIC_MODEL: Model name (default claude-sonnet-4-6)
    """

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self) -> None:
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        if not self._api_key:
            raise LLMError("claude", "ANTHROPIC_API_KEY env var is required")

    @property
    def name(self) -> str:
        return f"claude/{self._model}"

    async def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                resp = await client.post(
                    self.API_URL,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                # Extract text from first content block
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                raise LLMError("claude", "No text content in response")
        except httpx.HTTPError as e:
            raise LLMError("claude", str(e)) from e


class StubProvider(Provider):
    """Fixed-template provider for CI and testing.

    Returns deterministic SBAR-shaped text without any network calls.
    """

    TEMPLATE = (
        "S: Patient shows signs requiring clinical attention.\n"
        "B: Postoperative monitoring detected parameter changes.\n"
        "A: Deterministic screening criteria triggered.\n"
        "R: Review patient status and consider clinical evaluation."
    )

    @property
    def name(self) -> str:
        return "stub/template"

    async def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return self.TEMPLATE


def get_provider() -> Provider:
    """Factory: select provider from LLM_PROVIDER env var.

    Env var values: "ollama" (default), "groq", "claude", "stub".
    Falls back to Ollama if the requested provider cannot be initialized
    (e.g. missing API key).
    """
    provider_name = os.environ.get("LLM_PROVIDER", "ollama").lower().strip()

    if provider_name == "stub":
        return StubProvider()

    if provider_name == "groq":
        try:
            return GroqProvider()
        except LLMError:
            # Fallback to Ollama if key missing
            return OllamaProvider()

    if provider_name == "claude":
        try:
            return ClaudeProvider()
        except LLMError:
            # Fallback to Ollama if key missing
            return OllamaProvider()

    # Default: ollama
    return OllamaProvider()
