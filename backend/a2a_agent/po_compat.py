"""Bridge Prompt Opinion's gRPC-flavor A2A to the JSON-RPC spec form, both ways.

Inbound (PO → SDK): PO sends JSON-RPC envelopes with gRPC-style method names
(PascalCase, no slash) and UPPER_SNAKE_CASE enum values. The installed
``a2a-sdk`` only recognises the JSON-RPC spec form. We rewrite the body
before the SDK's request handler sees it.

Outbound (SDK → PO): the SDK serialises responses in spec form
(``result.kind="task"`` discriminator, ``status.state="completed"``,
``role="agent"``). PO's ``SendA2AMessage`` tool deserialises the
response with a proto-derived schema that expects the gRPC-flavor
shape: result wrapped in a ``task`` (or ``message``) oneof field, and
``TASK_STATE_*`` / ``ROLE_*`` enum values. We rewrite the response
after the SDK has built it.

Once the SDK ships native support — or PO adds spec-compliant aliases —
this module can be deleted and the import in ``app.py`` reverted.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("vigil.a2a.po_compat")

# Method-name mapping: gRPC-flavor (PO) → JSON-RPC spec (SDK).
#
# Source of truth — the canonical A2A protobuf:
#   https://raw.githubusercontent.com/a2aproject/A2A/main/specification/a2a.proto
# Search for ``rpc <Name>(...)`` declarations. Note the plurals (``ListTasks``,
# ``ListTaskPushNotificationConfigs``) and the ``Create*`` / ``Delete*``
# names — they are easy to typo. Refresh this table when the proto changes;
# delete the whole bridge once the a2a-sdk ships native gRPC-flavor support.
PO_METHOD_ALIASES: dict[str, str] = {
    "SendMessage": "message/send",
    "SendStreamingMessage": "message/stream",
    "GetTask": "tasks/get",
    "ListTasks": "tasks/list",
    "CancelTask": "tasks/cancel",
    "SubscribeToTask": "tasks/resubscribe",
    "CreateTaskPushNotificationConfig": "tasks/pushNotificationConfig/set",
    "GetTaskPushNotificationConfig": "tasks/pushNotificationConfig/get",
    "ListTaskPushNotificationConfigs": "tasks/pushNotificationConfig/list",
    "DeleteTaskPushNotificationConfig": "tasks/pushNotificationConfig/delete",
    "GetExtendedAgentCard": "agent/getAuthenticatedExtendedCard",
}

# Role-enum mapping (inbound: PO → spec). Verified against the proto:
#
#   enum Role {
#     ROLE_UNSPECIFIED = 0;
#     ROLE_USER = 1;
#     ROLE_AGENT = 2;
#   }
#
# ROLE_UNSPECIFIED is intentionally not mapped — let the SDK handle the
# default/error rather than silently translating a sentinel.
PO_ROLE_ALIASES: dict[str, str] = {
    "ROLE_USER": "user",
    "ROLE_AGENT": "agent",
}

# Reverse mappings for outbound responses (spec form → PO/gRPC-flavor).
PO_ROLE_REVERSE: dict[str, str] = {v: k for k, v in PO_ROLE_ALIASES.items()}

# TaskState enum — spec form (lowercase, dash-separated) → gRPC-flavor
# (UPPER_SNAKE with TASK_STATE_ prefix). Verified against the proto's
# ``enum TaskState { ... }`` block.
PO_TASK_STATE_REVERSE: dict[str, str] = {
    "submitted": "TASK_STATE_SUBMITTED",
    "working": "TASK_STATE_WORKING",
    "completed": "TASK_STATE_COMPLETED",
    "failed": "TASK_STATE_FAILED",
    "canceled": "TASK_STATE_CANCELED",
    "cancelled": "TASK_STATE_CANCELED",  # spelling alias — both forms appear in the wild
    "input-required": "TASK_STATE_INPUT_REQUIRED",
    "rejected": "TASK_STATE_REJECTED",
    "auth-required": "TASK_STATE_AUTH_REQUIRED",
    "unknown": "TASK_STATE_UNSPECIFIED",
    "": "TASK_STATE_UNSPECIFIED",
}


def _rewrite_roles(node: Any) -> int:
    """Walk a parsed JSON tree and rewrite any ``role`` value found.

    Returns the number of role values rewritten. Operates in place — call
    on a deep-copied tree to avoid mutating the caller's data.
    """
    rewritten = 0
    if isinstance(node, dict):
        role = node.get("role")
        if isinstance(role, str) and role in PO_ROLE_ALIASES:
            node["role"] = PO_ROLE_ALIASES[role]
            rewritten += 1
        for value in node.values():
            rewritten += _rewrite_roles(value)
    elif isinstance(node, list):
        for item in node:
            rewritten += _rewrite_roles(item)
    return rewritten


def _strip_stale_task_ids(node: Any) -> int:
    """Walk a parsed JSON tree and remove any ``taskId`` / ``task_id`` fields.

    Why: Prompt Opinion's General Chat agent threads multiple skill
    invocations onto the same A2A task id. Once Vigil emits
    ``TaskState.completed`` for the first skill (which it does on every
    reply — Option 3 chat is one-shot), the SDK's DefaultRequestHandler
    correctly rejects any follow-on message addressed to the same task
    with::

        Task <uuid> is in terminal state: completed

    Per A2A spec that's the right behaviour — a completed task is
    immutable. But the only A2A client we target (PO) doesn't mint a
    fresh task id per turn, so we get the rejection on every second
    invocation.

    Mitigation: strip every ``taskId`` reference from the inbound
    payload before the SDK sees it. The handler then mints a new
    task per request. Conversational continuation across tasks is
    lost — PO's chat itself doesn't use it, so no functional regression
    in the Option 3 surface. Logged for forensic clarity.

    Returns the count of stripped task-id keys (for log breadcrumbs).
    Operates in place — call on a deep-copied tree.
    """
    stripped = 0
    if isinstance(node, dict):
        for key in ("taskId", "task_id"):
            if key in node:
                node.pop(key, None)
                stripped += 1
        for value in list(node.values()):
            stripped += _strip_stale_task_ids(value)
    elif isinstance(node, list):
        for item in node:
            stripped += _strip_stale_task_ids(item)
    return stripped


def _rewrite_states_outbound(node: Any) -> int:
    """Walk a parsed JSON tree and rewrite TaskState values from spec
    form (``"completed"``) to gRPC-flavor (``"TASK_STATE_COMPLETED"``).

    Operates in place. Returns the count of rewrites for log breadcrumbs.
    Reverse counterpart of the inbound role rewriter.
    """
    rewritten = 0
    if isinstance(node, dict):
        state = node.get("state")
        if isinstance(state, str) and state in PO_TASK_STATE_REVERSE:
            mapped = PO_TASK_STATE_REVERSE[state]
            if mapped != state:
                node["state"] = mapped
                rewritten += 1
        # Reverse-map roles too — a Message embedded under task.status.message
        # carries ``role: "agent"`` from the spec, but PO expects ROLE_AGENT.
        role = node.get("role")
        if isinstance(role, str) and role in PO_ROLE_REVERSE:
            node["role"] = PO_ROLE_REVERSE[role]
            rewritten += 1
        for value in node.values():
            rewritten += _rewrite_states_outbound(value)
    elif isinstance(node, list):
        for item in node:
            rewritten += _rewrite_states_outbound(item)
    return rewritten


def normalise_po_response(body: dict[str, Any]) -> dict[str, Any]:
    """Translate a spec-form JSON-RPC response to PO/gRPC-flavor.

    Two transformations:

    1. **Wrap ``result`` in the proto oneof field.** The spec encodes
       ``SendMessageResponse.payload`` with a ``kind`` discriminator on
       the result object (``"task"`` or ``"message"``). The proto's
       ``oneof payload { Task task = 1; Message message = 2; }`` puts
       the discriminator in the field name itself. PO's deserialiser
       looks for ``response.result.task`` (or ``.message``) and errors
       out with ``"did not respond with a task"`` when our spec-form
       result has the fields directly under ``result``.

    2. **Reverse-map enum values.** ``state`` and ``role`` are spec-form
       lowercase / dash-separated (``"completed"``, ``"agent"``); PO
       expects gRPC-flavor (``"TASK_STATE_COMPLETED"``, ``"ROLE_AGENT"``).
       Recursive walk over the wrapped result.

    The ``kind`` discriminator is left intact after wrapping — PO's
    deserialiser ignores unknown fields by default. If a future PO bump
    starts rejecting them we can strip in a follow-up.

    Returns a NEW dict; does not mutate the input. Pure function — safe
    to unit test in isolation.
    """
    if not isinstance(body, dict):
        return body  # type: ignore[unreachable]

    # Only transform JSON-RPC responses with a ``result`` object. Errors
    # (with an ``error`` field) and notifications (no result) pass through.
    if "result" not in body:
        return copy.deepcopy(body)

    new_body = copy.deepcopy(body)
    result = new_body.get("result")
    if not isinstance(result, dict):
        return new_body

    # Wrap the result in the oneof field by ``kind`` discriminator.
    kind = result.get("kind")
    if kind == "task":
        new_body["result"] = {"task": result}
    elif kind == "message":
        new_body["result"] = {"message": result}
    # Unknown / missing kind — leave the structure as-is and let PO surface
    # whatever error it likes. Better than guessing wrong.

    # Reverse-map enum values across the wrapped tree. Counts are for
    # logging only; we don't bail on zero rewrites because a bare error
    # response might legitimately have no enums to rewrite.
    rewritten = _rewrite_states_outbound(new_body.get("result"))
    if rewritten:
        logger.info(
            "po_compat: rewrote outbound state/role values",
            extra={"count": rewritten},
        )

    return new_body


def normalise_po_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Translate a PO-flavor JSON-RPC payload to spec form.

    - Maps ``body['method']`` via :data:`PO_METHOD_ALIASES` (no-op if unknown).
    - Recursively maps any ``role`` value via :data:`PO_ROLE_ALIASES`
      anywhere in the payload (covers ``params.message.role`` and any
      nested message arrays such as ``params.history[*].role``).
    - Returns a NEW dict; does not mutate the input.

    Pure function — safe to unit test in isolation.
    """
    if not isinstance(body, dict):
        return body  # type: ignore[unreachable]

    new_body = copy.deepcopy(body)

    method = new_body.get("method")
    if isinstance(method, str) and method in PO_METHOD_ALIASES:
        new_method = PO_METHOD_ALIASES[method]
        new_body["method"] = new_method
        logger.info(
            "po_compat: rewrote method",
            extra={"from": method, "to": new_method},
        )

    rewritten = _rewrite_roles(new_body.get("params"))
    if rewritten:
        logger.info(
            "po_compat: rewrote role values",
            extra={"count": rewritten},
        )

    # Strip any taskId references from the inbound payload (PO's chat
    # agent reuses task ids across turns; Vigil's per-reply
    # TaskState.completed makes those references terminal and the SDK
    # rejects with "Task <uuid> is in terminal state: completed"). See
    # the _strip_stale_task_ids docstring for the full rationale.
    stripped = _strip_stale_task_ids(new_body.get("params"))
    if stripped:
        logger.info(
            "po_compat: stripped stale task id reference(s) — "
            "fresh task will be minted",
            extra={"count": stripped},
        )

    return new_body


class PoCompatMiddleware(BaseHTTPMiddleware):
    """Intercept ``POST {path}``, normalise PO-flavor JSON-RPC, forward.

    Only acts on POSTs to the configured JSON-RPC mount path. Anything else
    passes through untouched. Malformed JSON also passes through — the
    SDK's own parser will return a JSON-RPC parse error.
    """

    def __init__(self, app: Any, path: str = "/a2a") -> None:
        super().__init__(app)
        self._path = path

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method != "POST" or request.url.path != self._path:
            return await call_next(request)

        raw = await request.body()
        if not raw:
            return await call_next(request)

        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Replay the original bytes so the SDK can return its own
            # JSON-RPC -32700 parse error.
            await self._replace_body(request, raw)
            response = await call_next(request)
            return await self._transform_response(response)

        if not isinstance(body, dict):
            await self._replace_body(request, raw)
            response = await call_next(request)
            return await self._transform_response(response)

        new_body = normalise_po_payload(body)
        if new_body == body:
            # Nothing to rewrite inbound — replay original bytes verbatim,
            # but still transform the outbound response (PO expects
            # gRPC-flavor regardless of what shape the request was in).
            await self._replace_body(request, raw)
            response = await call_next(request)
            return await self._transform_response(response)

        new_raw = json.dumps(new_body).encode("utf-8")
        await self._replace_body(request, new_raw)
        response = await call_next(request)
        return await self._transform_response(response)

    @staticmethod
    async def _transform_response(response: Response) -> Response:
        """Rewrite the JSON-RPC response body from spec form to PO/gRPC-flavor.

        Only acts on JSON-content responses. Streaming and non-JSON
        responses pass through untouched (the SDK doesn't stream
        ``message/send`` responses today, but ``message/stream`` would —
        defer that bridge work until we see streaming traffic from PO).
        """
        media_type = (response.headers.get("content-type") or "").split(";")[0].strip()
        if media_type != "application/json":
            return response

        # Read the entire response body. BaseHTTPMiddleware exposes it
        # via ``response.body_iterator`` even for non-streaming responses.
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        raw_body = b"".join(chunks)

        if not raw_body:
            return response

        try:
            parsed = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            # Hand back the original bytes — don't double-encode.
            return Response(
                content=raw_body,
                status_code=response.status_code,
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() != "content-length"
                },
                media_type=response.media_type,
            )

        if not isinstance(parsed, dict):
            return Response(
                content=raw_body,
                status_code=response.status_code,
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() != "content-length"
                },
                media_type=response.media_type,
            )

        new_parsed = normalise_po_response(parsed)
        new_raw = json.dumps(new_parsed).encode("utf-8")

        return Response(
            content=new_raw,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
            media_type=response.media_type,
        )

    @staticmethod
    async def _replace_body(request: Request, body: bytes) -> None:
        """Make ``body`` what the next handler will read.

        Starlette caches the parsed body on ``request._body`` and reads
        the raw stream via ``request._receive``. Override both so any
        downstream code path — cached body access OR streaming — sees the
        new bytes.
        """
        request._body = body  # type: ignore[attr-defined]

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]

        # Keep Content-Length consistent so downstream parsers honour it.
        headers = MutableHeaders(scope=request.scope)
        headers["content-length"] = str(len(body))
