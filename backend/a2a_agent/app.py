"""Vigil A2A agent application bootstrap.

Builds the A2A FastAPI application serving:
- AgentCard at GET /.well-known/agent-card.json
- JSON-RPC endpoint at POST /a2a
- Optional polling loop (POLL_INTERVAL_SEC env, default 900s, demo 30s)

Reference: PROMPT_OPINION_INTEGRATION.md §3.3, BUILD_PLAN.md B7
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard

from backend.a2a_agent.mcp_client import VigilMcpClient
from backend.a2a_agent.sentinel import PostopSentinelExecutor

logger = logging.getLogger("vigil.a2a.app")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

A2A_PORT = int(os.environ.get("A2A_PORT", "9000"))
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "900"))

# ---------------------------------------------------------------------------
# AgentCard — load from JSON file
# ---------------------------------------------------------------------------

_card_path = Path(__file__).parent / "agent_card.json"
_card_data = json.loads(_card_path.read_text())

# Override URL from env if deploying publicly
if os.environ.get("A2A_PUBLIC_URL"):
    _card_data["url"] = os.environ["A2A_PUBLIC_URL"]

agent_card = AgentCard.model_validate(_card_data)

# ---------------------------------------------------------------------------
# Wire up executor → handler → application
# ---------------------------------------------------------------------------

mcp_client = VigilMcpClient()
executor = PostopSentinelExecutor(mcp=mcp_client)
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=task_store,
)

app_builder = A2AFastAPIApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)

app = app_builder.build()

logger.info(
    "Vigil A2A agent configured",
    extra={
        "port": A2A_PORT,
        "poll_interval_sec": POLL_INTERVAL_SEC,
        "mcp_url": mcp_client._base_url,
    },
)

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.a2a_agent.app:app",
        host="0.0.0.0",
        port=A2A_PORT,
        log_level="info",
    )
