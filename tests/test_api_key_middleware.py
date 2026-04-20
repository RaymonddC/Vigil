"""Tests for API key middleware (H1) and bearer token log filter (H3).

Covers:
- Dev mode: VIGIL_API_KEY unset → all requests pass
- Enforced mode: valid key passes, invalid/missing key → 401
- Exempt paths bypass key check even when key is set
- Bearer token in a log record is redacted by _BearerTokenFilter
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from backend.obs.logging import _BearerTokenFilter
from backend.security.api_key import build_api_key_middleware

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _make_app(
    skip_prefixes: tuple[str, ...] = ("/health", "/docs", "/openapi.json", "/redoc"),
) -> FastAPI:
    test_app = FastAPI()
    test_app.middleware("http")(build_api_key_middleware(skip_prefixes=skip_prefixes))

    @test_app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @test_app.get("/protected")
    async def protected():
        return JSONResponse({"status": "protected_reached"})

    return test_app


@pytest.fixture
def client():
    transport = ASGITransport(app=_make_app())
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Dev mode — VIGIL_API_KEY unset
# ---------------------------------------------------------------------------


class TestDevMode:
    async def test_all_requests_pass_without_key(self, client, monkeypatch):
        """When VIGIL_API_KEY is unset, all requests are allowed through."""
        monkeypatch.delenv("VIGIL_API_KEY", raising=False)
        async with client:
            resp = await client.get("/protected")
        assert resp.status_code == 200

    async def test_exempt_path_passes_without_key(self, client, monkeypatch):
        """Exempt path passes when no key is configured."""
        monkeypatch.delenv("VIGIL_API_KEY", raising=False)
        async with client:
            resp = await client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Enforced mode — VIGIL_API_KEY set
# ---------------------------------------------------------------------------


class TestEnforcedMode:
    async def test_valid_key_passes(self, client, monkeypatch):
        """Correct X-API-Key header is allowed through."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with client:
            resp = await client.get("/protected", headers={"X-API-Key": "test-secret-key-xyz"})
        assert resp.status_code == 200

    async def test_invalid_key_rejected(self, client, monkeypatch):
        """Wrong X-API-Key → 401 Unauthorized."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with client:
            resp = await client.get("/protected", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401
        assert resp.json()["error"] == "Unauthorized"

    async def test_missing_key_header_rejected(self, client, monkeypatch):
        """No X-API-Key header when key is enforced → 401."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with client:
            resp = await client.get("/protected")
        assert resp.status_code == 401

    async def test_empty_key_header_rejected(self, client, monkeypatch):
        """Empty X-API-Key header → 401."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with client:
            resp = await client.get("/protected", headers={"X-API-Key": ""})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Exempt paths
# ---------------------------------------------------------------------------


class TestExemptPaths:
    async def test_health_exempt_when_key_set(self, client, monkeypatch):
        """/health passes without X-API-Key even when enforcement is active."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with client:
            resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_docs_exempt_when_key_set(self, monkeypatch):
        """/docs passes without X-API-Key when enforcement is active."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://test"
        ) as c:
            resp = await c.get("/docs")
        assert resp.status_code == 200

    async def test_openapi_exempt_when_key_set(self, monkeypatch):
        """/openapi.json passes without X-API-Key when enforcement is active."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        async with AsyncClient(
            transport=ASGITransport(app=_make_app()), base_url="http://test"
        ) as c:
            resp = await c.get("/openapi.json")
        assert resp.status_code == 200

    async def test_agent_card_exempt(self, monkeypatch):
        """/.well-known/agent-card.json passes without X-API-Key (A2A spec)."""
        monkeypatch.setenv("VIGIL_API_KEY", "test-secret-key-xyz")
        a2a_skip = ("/.well-known/agent-card.json", "/docs", "/openapi.json")
        app = FastAPI()
        app.middleware("http")(build_api_key_middleware(skip_prefixes=a2a_skip))

        @app.get("/.well-known/agent-card.json")
        async def agent_card():
            return JSONResponse({"name": "vigil"})

        @app.get("/a2a")
        async def a2a():
            return JSONResponse({"status": "reached"})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            card_resp = await c.get("/.well-known/agent-card.json")
            protected_resp = await c.get("/a2a")

        assert card_resp.status_code == 200
        assert protected_resp.status_code == 401


# ---------------------------------------------------------------------------
# H3 — Bearer token filter
# ---------------------------------------------------------------------------


class TestBearerTokenFilter:
    def test_bearer_token_redacted_in_message(self):
        """Bearer token in log record msg is replaced with [REDACTED]."""
        log_filter = _BearerTokenFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Authorization: Bearer abc123defghij",
            args=(),
            exc_info=None,
        )
        log_filter.filter(record)
        assert "abc123defghij" not in record.msg
        assert "[REDACTED]" in record.msg
        assert "Bearer" in record.msg

    def test_bearer_token_redacted_in_tuple_args(self):
        """Bearer token in log record args tuple is also redacted."""
        log_filter = _BearerTokenFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Token: %s",
            args=("Bearer secrettoken12345",),
            exc_info=None,
        )
        log_filter.filter(record)
        assert "secrettoken12345" not in str(record.args)
        assert "[REDACTED]" in str(record.args)

    def test_bearer_token_redacted_in_dict_args(self):
        """Bearer token in log record args dict values is also redacted."""
        log_filter = _BearerTokenFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="headers: %(auth)s",
            args=(),
            exc_info=None,
        )
        # Set dict args directly to simulate the %(key)s substitution path.
        record.args = {"auth": "Bearer xfhiraccesstoken9999"}
        log_filter.filter(record)
        assert "xfhiraccesstoken9999" not in str(record.args)
        assert "[REDACTED]" in str(record.args)

    def test_no_token_passes_through(self):
        """Log records without bearer tokens are not modified."""
        log_filter = _BearerTokenFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Patient PT-001 vitals checked",
            args=(),
            exc_info=None,
        )
        original_msg = record.msg
        log_filter.filter(record)
        assert record.msg == original_msg
