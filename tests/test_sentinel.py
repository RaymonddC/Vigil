"""Tests for the A2A executor's helper utilities and Option-3 contract.

Slice A re-targets the A2A executor at request-response skill dispatch.
The historical "always enqueue on trigger" coverage that lived in this
file has moved to ``tests/test_a2a_skill_dispatch.py`` because the
queue-write side effect now belongs only to the autonomous tick path
(``backend/a2a_agent/tick.py``) — see ``run_cycle_for_patient`` and its
own coverage in ``tests/test_tick.py``.

What remains here:
  - shape coverage for ``_unwrap_tool_result`` (used by both paths)
  - a guard that the A2A executor module itself does NOT depend on
    the review-queue write path. If someone re-wires it, this test
    will catch the regression.
"""

from __future__ import annotations

import json

from backend.a2a_agent import sentinel
from backend.a2a_agent.sentinel import _unwrap_tool_result

# ---------------------------------------------------------------------------
# _unwrap_tool_result: shape coverage
# ---------------------------------------------------------------------------


class TestUnwrapToolResult:
    def test_mcp_content_wrapped(self) -> None:
        wrapped = {
            "content": [
                {"type": "text", "text": json.dumps({"severity": "critical"})}
            ],
            "isError": False,
        }
        assert _unwrap_tool_result(wrapped) == {"severity": "critical"}

    def test_plain_dict_passthrough(self) -> None:
        assert _unwrap_tool_result({"severity": "info"}) == {"severity": "info"}

    def test_json_string(self) -> None:
        assert _unwrap_tool_result('{"a": 1}') == {"a": 1}

    def test_malformed_returns_empty(self) -> None:
        assert _unwrap_tool_result("not-json") == {}
        assert _unwrap_tool_result(None) == {}
        assert _unwrap_tool_result(12345) == {}


# ---------------------------------------------------------------------------
# Option-3 invariant: the A2A executor must not enqueue.
# ---------------------------------------------------------------------------


class TestNoQueueWriteFromExecutor:
    """Slice A locks in: ``vigil.draft_sbar`` returns the SBAR text and
    completes the A2A task; it does NOT enqueue to the SQLite review
    queue. Prompt Opinion's general chat is the human-in-the-loop in
    Option 3. The autonomous loop (``backend/a2a_agent/tick.py``) keeps
    the enqueue side effect for the dashboard surface.
    """

    def test_sentinel_module_does_not_import_enqueue_alert(self) -> None:
        # Direct symbol check — quick regression guard if someone
        # accidentally re-wires the queue write into the executor.
        assert not hasattr(sentinel, "enqueue_alert"), (
            "PostopSentinelExecutor must not import enqueue_alert; "
            "queue writes belong to backend/a2a_agent/tick.py."
        )
