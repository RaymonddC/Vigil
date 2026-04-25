"""Tests for the A2A agent's outbound MCP HTTP client.

Focus: SEC-05 — when ``VIGIL_API_KEY`` is configured, every outbound MCP
request must carry the ``X-API-Key`` header so the MCP server's shared
api-key middleware accepts it. When the env var is unset (local dev),
no header should be injected — the middleware logs a warning and
allows the request through, and we want to keep that behavior.

Mirrors the pytest-asyncio + monkeypatch style used in
``tests/test_a2a_skill_dispatch.py``.
"""

from __future__ import annotations

import httpx
import pytest

from backend.a2a_agent.mcp_client import VigilMcpClient


def _ok_handler(captured: list[httpx.Request]):
    """Build a MockTransport handler that records the request and returns
    a minimal valid JSON-RPC tools/call response."""

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "test",
                "result": {"content": [], "isError": False},
            },
            headers={"content-type": "application/json"},
        )

    return _handler


def _patch_async_client(monkeypatch, transport: httpx.MockTransport) -> None:
    """Force ``mcp_client``'s httpx.AsyncClient to use our MockTransport."""
    real_cls = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(
        "backend.a2a_agent.mcp_client.httpx.AsyncClient", _factory
    )


@pytest.mark.asyncio
async def test_call_tool_forwards_api_key_when_env_set(monkeypatch) -> None:
    """When VIGIL_API_KEY is set, X-API-Key must appear on every MCP call."""
    monkeypatch.setenv("VIGIL_API_KEY", "test-key")
    captured: list[httpx.Request] = []
    _patch_async_client(monkeypatch, httpx.MockTransport(_ok_handler(captured)))

    client = VigilMcpClient(base_url="http://mcp.test")
    await client.call_tool("screen_vital_thresholds", arguments={"patient_id": "PT-007"})

    assert len(captured) == 1
    assert captured[0].headers.get("X-API-Key") == "test-key"


@pytest.mark.asyncio
async def test_call_tool_omits_api_key_when_env_unset(monkeypatch) -> None:
    """Local-dev path: no env var means no header — middleware allows it."""
    monkeypatch.delenv("VIGIL_API_KEY", raising=False)
    captured: list[httpx.Request] = []
    _patch_async_client(monkeypatch, httpx.MockTransport(_ok_handler(captured)))

    client = VigilMcpClient(base_url="http://mcp.test")
    await client.call_tool("screen_vital_thresholds", arguments={"patient_id": "PT-007"})

    assert len(captured) == 1
    assert "X-API-Key" not in captured[0].headers


@pytest.mark.asyncio
async def test_call_tool_does_not_let_sharp_clobber_api_key(monkeypatch) -> None:
    """Defensive: a malformed sharp_headers payload cannot overwrite the key."""
    monkeypatch.setenv("VIGIL_API_KEY", "real-key")
    captured: list[httpx.Request] = []
    _patch_async_client(monkeypatch, httpx.MockTransport(_ok_handler(captured)))

    client = VigilMcpClient(base_url="http://mcp.test")
    await client.call_tool(
        "screen_vital_thresholds",
        arguments={"patient_id": "PT-007"},
        sharp_headers={"X-API-Key": "evil", "x-fhir-server-url": "http://fhir"},
    )

    assert len(captured) == 1
    assert captured[0].headers.get("X-API-Key") == "real-key"
    # SHARP headers still flow through.
    assert captured[0].headers.get("x-fhir-server-url") == "http://fhir"
