"""Thin httpx wrapper for calling Vigil MCP tools from the A2A agent.

Forwards the 3 SHARP headers onto every MCP tool call. The MCP server
is at localhost:7001 by default (VIGIL_MCP_URL env var).

Reference: PROMPT_OPINION_INTEGRATION.md §3.4, BUILD_PLAN.md B7
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("vigil.a2a.mcp_client")

DEFAULT_MCP_URL = "http://localhost:7001"


class McpClientError(Exception):
    """Raised when an MCP tool call fails."""

    def __init__(self, tool: str, message: str, status_code: int | None = None):
        super().__init__(f"MCP tool '{tool}' failed: {message}")
        self.tool = tool
        self.status_code = status_code


class VigilMcpClient:
    """Async HTTP client for calling Vigil MCP tools.

    Each call sends a JSON-RPC request to the MCP server's streamable
    HTTP endpoint, forwarding SHARP headers for FHIR context.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (
            base_url
            or os.environ.get("VIGIL_MCP_URL", DEFAULT_MCP_URL)
        ).rstrip("/")

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        sharp_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Invoke an MCP tool and return its parsed JSON result.

        Args:
            tool_name: Name of the MCP tool (e.g. "screen_vital_thresholds").
            arguments: Tool input arguments.
            sharp_headers: SHARP headers to forward (x-fhir-server-url, etc.).

        Returns:
            Parsed JSON result from the tool.

        Raises:
            McpClientError: On any failure.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if sharp_headers:
            headers.update(sharp_headers)

        # MCP streamable HTTP uses JSON-RPC
        payload = {
            "jsonrpc": "2.0",
            "id": f"vigil-agent-{tool_name}-{int(time.time())}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/mcp",
                    json=payload,
                    headers=headers,
                )
                duration_ms = round((time.monotonic() - start) * 1000, 1)

                if resp.status_code >= 400:
                    logger.error(
                        "MCP tool HTTP error",
                        extra={
                            "tool": tool_name,
                            "status_code": resp.status_code,
                            "duration_ms": duration_ms,
                        },
                    )
                    raise McpClientError(
                        tool_name,
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                result = resp.json()
                logger.info(
                    "MCP tool call completed",
                    extra={
                        "tool": tool_name,
                        "duration_ms": duration_ms,
                    },
                )

                # JSON-RPC response: extract result or error
                if "error" in result:
                    raise McpClientError(
                        tool_name,
                        result["error"].get("message", "Unknown MCP error"),
                    )

                return result.get("result", result)

        except httpx.HTTPError as e:
            raise McpClientError(tool_name, str(e)) from e
