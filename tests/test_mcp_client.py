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

from backend.a2a_agent.mcp_client import DEFAULT_MCP_URL, VigilMcpClient


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


@pytest.mark.parametrize(
    ("ctor_arg", "mcp_base_url", "vigil_mcp_url", "expected"),
    [
        # 1. Explicit constructor arg always wins, even over both env vars.
        (
            "http://explicit.test",
            "http://from-mcp-base.test",
            "http://from-vigil-mcp.test",
            "http://explicit.test",
        ),
        # 2. MCP_BASE_URL (canonical, matches docker-compose) wins over the
        #    legacy VIGIL_MCP_URL fallback.
        (
            None,
            "http://from-mcp-base.test",
            "http://from-vigil-mcp.test",
            "http://from-mcp-base.test",
        ),
        # 3. VIGIL_MCP_URL is honored when MCP_BASE_URL is unset
        #    (back-compat for existing local .env files).
        (
            None,
            None,
            "http://from-vigil-mcp.test",
            "http://from-vigil-mcp.test",
        ),
        # 4. With nothing set, fall back to DEFAULT_MCP_URL.
        (None, None, None, DEFAULT_MCP_URL),
        # 5. Trailing slashes are stripped regardless of source.
        (
            None,
            "http://from-mcp-base.test/",
            None,
            "http://from-mcp-base.test",
        ),
    ],
    ids=[
        "ctor-arg-wins",
        "mcp-base-url-over-vigil-mcp-url",
        "vigil-mcp-url-fallback",
        "default-when-nothing-set",
        "trailing-slash-stripped",
    ],
)
def test_base_url_precedence(
    monkeypatch,
    ctor_arg: str | None,
    mcp_base_url: str | None,
    vigil_mcp_url: str | None,
    expected: str,
) -> None:
    """Base-URL resolution precedence: ctor arg > MCP_BASE_URL > VIGIL_MCP_URL > default.

    Regression test for the deploy-blocking env var name mismatch where the
    agent fell back to ``localhost:7001`` in docker-compose because it was
    only reading the legacy ``VIGIL_MCP_URL`` while compose set the
    canonical ``MCP_BASE_URL``.
    """
    if mcp_base_url is None:
        monkeypatch.delenv("MCP_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("MCP_BASE_URL", mcp_base_url)
    if vigil_mcp_url is None:
        monkeypatch.delenv("VIGIL_MCP_URL", raising=False)
    else:
        monkeypatch.setenv("VIGIL_MCP_URL", vigil_mcp_url)

    client = VigilMcpClient(base_url=ctor_arg)
    assert client._base_url == expected
