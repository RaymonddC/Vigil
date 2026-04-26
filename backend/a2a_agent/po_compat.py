"""Bridge Prompt Opinion's gRPC-flavor A2A to the JSON-RPC spec form.

PO sends JSON-RPC envelopes with gRPC-style method names (PascalCase, no
slash) and UPPER_SNAKE_CASE enum values. The installed ``a2a-sdk`` only
recognises the JSON-RPC spec method names. This middleware normalises
inbound requests so the SDK can dispatch them.

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

# Role-enum mapping. Verified against the proto:
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
            return await call_next(request)

        if not isinstance(body, dict):
            await self._replace_body(request, raw)
            return await call_next(request)

        new_body = normalise_po_payload(body)
        if new_body == body:
            # Nothing to rewrite — replay original bytes verbatim.
            await self._replace_body(request, raw)
            return await call_next(request)

        new_raw = json.dumps(new_body).encode("utf-8")
        await self._replace_body(request, new_raw)
        return await call_next(request)

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
