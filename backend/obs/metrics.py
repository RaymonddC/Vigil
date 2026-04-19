"""In-memory event store + tool-call timing + LLM token counters.

The event store feeds the ``GET /api/events/tail?since=<ts>`` polling endpoint
consumed by the frontend Timeline view (FE3). It lives in process memory —
it survives page reloads but not server restarts, which is fine for demo use.

Events are emitted by:
- tool_call_timer()  — async context manager; wraps any MCP tool call
- record_llm_call()  — called after each LLM completion
- append_event()     — low-level; used by the A2A agent for state transitions

Store is bounded at MAX_EVENTS (FIFO eviction) to avoid unbounded growth.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.obs.logging import get_logger, get_request_id

logger = get_logger(__name__)

MAX_EVENTS: int = 2000

# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


@dataclass
class VigilEvent:
    """One structured event in the tail store."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    event_type: str = ""   # "tool_call" | "agent_state" | "llm_call"
    request_id: str = ""
    patient_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shared mutable state
# ---------------------------------------------------------------------------

_lock: asyncio.Lock = asyncio.Lock()
_events: list[VigilEvent] = []

_llm_tokens_prompt: int = 0
_llm_tokens_completion: int = 0


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


async def append_event(
    event_type: str,
    payload: dict[str, Any],
    patient_id: str | None = None,
) -> VigilEvent:
    """Append an event to the in-memory store.

    Thread-safe via asyncio lock. FIFO-evicts oldest entries when the store
    exceeds MAX_EVENTS.
    """
    event = VigilEvent(
        event_type=event_type,
        request_id=get_request_id(),
        patient_id=patient_id,
        payload=payload,
    )
    async with _lock:
        _events.append(event)
        if len(_events) > MAX_EVENTS:
            del _events[: len(_events) - MAX_EVENTS]
    return event


async def get_events_since(since: str | None) -> list[dict[str, Any]]:
    """Return serialised events newer than *since* (ISO timestamp string).

    If *since* is None or unparseable, all stored events are returned.
    Called by ``GET /api/events/tail?since=<ts>``.
    """
    cutoff: datetime | None = None
    if since:
        try:
            cutoff = datetime.fromisoformat(since)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=UTC)
        except ValueError:
            pass

    async with _lock:
        snapshot = list(_events)

    if cutoff is None:
        return [_to_dict(e) for e in snapshot]

    return [
        _to_dict(e)
        for e in snapshot
        if datetime.fromisoformat(e.ts) > cutoff
    ]


def _to_dict(e: VigilEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "ts": e.ts,
        "event_type": e.event_type,
        "request_id": e.request_id,
        "patient_id": e.patient_id,
        "payload": e.payload,
    }


# ---------------------------------------------------------------------------
# tool_call_timer context manager
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def tool_call_timer(
    tool_name: str,
    patient_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async CM that records tool-call duration and status as a VigilEvent.

    Usage::

        async with tool_call_timer("screen_vital_thresholds", patient_id) as ctx:
            result = await do_work()
            ctx["status"] = result.status   # optional override

    On normal exit: logs duration + status.
    On exception: sets status="error" and re-raises.
    """
    start = time.perf_counter()
    ctx: dict[str, Any] = {"status": "ok"}
    try:
        yield ctx
    except Exception as exc:
        ctx["status"] = "error"
        ctx["error"] = str(exc)
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        payload: dict[str, Any] = {
            "tool": tool_name,
            "duration_ms": duration_ms,
            "status": ctx.get("status", "ok"),
        }
        if "error" in ctx:
            payload["error"] = ctx["error"]
        await append_event("tool_call", payload, patient_id=patient_id)
        logger.info(
            "tool_call",
            extra={
                "_vigil_tool": tool_name,
                "_vigil_duration_ms": duration_ms,
                "_vigil_status": payload["status"],
                "_vigil_patient_id": patient_id or "",
            },
        )


# ---------------------------------------------------------------------------
# LLM token accounting
# ---------------------------------------------------------------------------


async def record_llm_call(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    patient_id: str | None = None,
) -> None:
    """Increment cumulative LLM token counters and emit a VigilEvent."""
    global _llm_tokens_prompt, _llm_tokens_completion
    _llm_tokens_prompt += prompt_tokens
    _llm_tokens_completion += completion_tokens
    await append_event(
        "llm_call",
        {
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        patient_id=patient_id,
    )
    logger.info(
        "llm_call",
        extra={
            "_vigil_provider": provider,
            "_vigil_model": model,
            "_vigil_prompt_tokens": prompt_tokens,
            "_vigil_completion_tokens": completion_tokens,
        },
    )


def get_token_totals() -> dict[str, int]:
    """Return cumulative LLM token counts since server start."""
    return {
        "prompt_tokens": _llm_tokens_prompt,
        "completion_tokens": _llm_tokens_completion,
        "total_tokens": _llm_tokens_prompt + _llm_tokens_completion,
    }
