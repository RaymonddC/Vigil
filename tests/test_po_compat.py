"""Tests for the Prompt Opinion compatibility middleware.

Two layers:

1. :func:`normalise_po_payload` — pure function, no I/O. Verifies all 7
   PascalCase → spec method aliases, role enum mappings, defensive walks
   into nested message arrays, and that the input dict is not mutated.

2. :class:`PoCompatMiddleware` — wired onto a FastAPI test app with an
   echo route at ``/a2a`` that returns whatever JSON it receives. Verifies
   that downstream handlers see the rewritten body, that other paths /
   methods are not touched, that malformed JSON passes through, and that
   an INFO log is emitted on rewrite.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from backend.a2a_agent.po_compat import (
    PO_METHOD_ALIASES,
    PO_ROLE_ALIASES,
    PoCompatMiddleware,
    normalise_po_payload,
)

# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


class TestMethodAliases:
    """Each of the 11 PO PascalCase methods → JSON-RPC slash form.

    Verified against the canonical A2A protobuf:
    https://raw.githubusercontent.com/a2aproject/A2A/main/specification/a2a.proto
    """

    def _rewrite(self, method: str) -> str:
        body = {"jsonrpc": "2.0", "id": "1", "method": method, "params": {}}
        return normalise_po_payload(body)["method"]

    def test_send_message_alias(self) -> None:
        assert self._rewrite("SendMessage") == "message/send"

    def test_send_streaming_message_alias(self) -> None:
        assert self._rewrite("SendStreamingMessage") == "message/stream"

    def test_get_task_alias(self) -> None:
        assert self._rewrite("GetTask") == "tasks/get"

    def test_list_tasks_alias(self) -> None:
        assert self._rewrite("ListTasks") == "tasks/list"

    def test_cancel_task_alias(self) -> None:
        assert self._rewrite("CancelTask") == "tasks/cancel"

    def test_subscribe_to_task_alias(self) -> None:
        assert self._rewrite("SubscribeToTask") == "tasks/resubscribe"

    def test_create_push_notification_config_alias(self) -> None:
        assert (
            self._rewrite("CreateTaskPushNotificationConfig")
            == "tasks/pushNotificationConfig/set"
        )

    def test_get_push_notification_config_alias(self) -> None:
        assert (
            self._rewrite("GetTaskPushNotificationConfig")
            == "tasks/pushNotificationConfig/get"
        )

    def test_list_push_notification_configs_alias(self) -> None:
        """Note the PLURAL ``Configs`` — easy to typo as singular."""
        assert (
            self._rewrite("ListTaskPushNotificationConfigs")
            == "tasks/pushNotificationConfig/list"
        )

    def test_singular_list_push_notification_config_is_unknown(self) -> None:
        """Guard against the singular-typo regression. The proto name
        is ``ListTaskPushNotificationConfigs`` (plural Configs); the
        singular form must NOT be silently rewritten."""
        assert (
            self._rewrite("ListTaskPushNotificationConfig")
            == "ListTaskPushNotificationConfig"
        )

    def test_delete_push_notification_config_alias(self) -> None:
        assert (
            self._rewrite("DeleteTaskPushNotificationConfig")
            == "tasks/pushNotificationConfig/delete"
        )

    def test_get_extended_agent_card_alias(self) -> None:
        assert (
            self._rewrite("GetExtendedAgentCard")
            == "agent/getAuthenticatedExtendedCard"
        )

    def test_alias_table_has_eleven_entries(self) -> None:
        """Lock the public surface so additions are explicit."""
        assert len(PO_METHOD_ALIASES) == 11

    def test_alias_table_matches_proto(self) -> None:
        """Full snapshot of the proto-derived mapping. Update this with
        intent when the proto changes upstream."""
        assert PO_METHOD_ALIASES == {
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

    def test_unknown_method_passes_through(self) -> None:
        assert self._rewrite("Frobnicate") == "Frobnicate"

    def test_spec_form_method_passes_through(self) -> None:
        """Already-spec-form methods stay verbatim — idempotent."""
        assert self._rewrite("message/send") == "message/send"


# ---------------------------------------------------------------------------
# Role enum mapping
# ---------------------------------------------------------------------------


class TestRoleAliases:
    def test_role_user_mapped(self) -> None:
        body = {
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_USER", "parts": []}},
        }
        out = normalise_po_payload(body)
        assert out["params"]["message"]["role"] == "user"

    def test_role_agent_mapped(self) -> None:
        body = {
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_AGENT", "parts": []}},
        }
        out = normalise_po_payload(body)
        assert out["params"]["message"]["role"] == "agent"

    def test_unknown_role_passes_through(self) -> None:
        body = {
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_TOOL", "parts": []}},
        }
        out = normalise_po_payload(body)
        assert out["params"]["message"]["role"] == "ROLE_TOOL"

    def test_role_in_nested_history_array_mapped(self) -> None:
        """Some methods (history responses) embed lists of messages."""
        body = {
            "method": "SendMessage",
            "params": {
                "message": {"role": "ROLE_USER", "parts": []},
                "history": [
                    {"role": "ROLE_USER", "parts": []},
                    {"role": "ROLE_AGENT", "parts": []},
                ],
            },
        }
        out = normalise_po_payload(body)
        assert out["params"]["message"]["role"] == "user"
        assert out["params"]["history"][0]["role"] == "user"
        assert out["params"]["history"][1]["role"] == "agent"

    def test_role_alias_table(self) -> None:
        assert PO_ROLE_ALIASES == {"ROLE_USER": "user", "ROLE_AGENT": "agent"}


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_missing_message_does_not_error(self) -> None:
        body = {"jsonrpc": "2.0", "id": "1", "method": "GetTask", "params": {"id": "t1"}}
        out = normalise_po_payload(body)
        assert out["method"] == "tasks/get"
        assert out["params"] == {"id": "t1"}

    def test_missing_params_does_not_error(self) -> None:
        body = {"jsonrpc": "2.0", "id": "1", "method": "SendMessage"}
        out = normalise_po_payload(body)
        assert out["method"] == "message/send"
        assert "params" not in out

    def test_input_not_mutated(self) -> None:
        """Caller's dict is never modified — deep-copied."""
        body = {
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]}},
        }
        original = json.loads(json.dumps(body))  # deep snapshot
        out = normalise_po_payload(body)

        assert body == original, "input dict was mutated"
        # Object identity: the message dict in the output is NOT the same
        # object as the message dict in the input.
        assert out["params"]["message"] is not body["params"]["message"]

    def test_full_po_payload_round_trip(self) -> None:
        """The exact body shape PO sends on the wire."""
        body = {
            "jsonrpc": "2.0",
            "id": "bd6956d0-02d0-4da1-b437-31405a608e91",
            "method": "SendMessage",
            "params": {
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "Please screen the vitals."}],
                    "messageId": "ad226891-8636-4e49-9b53-5366fa58f8c8",
                    "metadata": {
                        "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context": {
                            "fhirUrl": "https://example/fhir",
                            "patientId": "abb130a6",
                        }
                    },
                }
            },
        }
        out = normalise_po_payload(body)
        assert out["method"] == "message/send"
        assert out["params"]["message"]["role"] == "user"
        # Untouched fields preserved verbatim
        assert out["id"] == body["id"]
        assert out["params"]["message"]["messageId"] == body["params"]["message"]["messageId"]
        assert (
            out["params"]["message"]["metadata"]
            == body["params"]["message"]["metadata"]
        )


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Test app: PoCompatMiddleware around two echo routes.

    The /a2a POST handler reads the body and returns it verbatim, so we
    can assert that the middleware's rewrite actually reached the handler.
    """
    app = FastAPI()
    app.add_middleware(PoCompatMiddleware)

    @app.post("/a2a")
    async def echo(request: Request) -> JSONResponse:
        body = await request.json()
        return JSONResponse(body)

    @app.get("/a2a")
    async def get_a2a() -> JSONResponse:
        return JSONResponse({"ok": True, "method": "GET"})

    @app.get("/.well-known/agent-card.json")
    async def card() -> JSONResponse:
        return JSONResponse({"name": "vigil"})

    @app.post("/.well-known/agent-card.json")
    async def card_post(request: Request) -> JSONResponse:
        body = await request.json()
        return JSONResponse(body)

    return app


@pytest.fixture
def app() -> FastAPI:
    return _make_app()


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestMiddleware:
    @pytest.mark.asyncio
    async def test_post_a2a_with_po_body_is_rewritten(
        self, client: AsyncClient
    ) -> None:
        po_body = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "hello"}],
                }
            },
        }
        async with client:
            resp = await client.post("/a2a", json=po_body)
        assert resp.status_code == 200
        downstream = resp.json()
        assert downstream["method"] == "message/send"
        assert downstream["params"]["message"]["role"] == "user"

    @pytest.mark.asyncio
    async def test_post_a2a_with_spec_body_is_unchanged(
        self, client: AsyncClient
    ) -> None:
        spec_body = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {"role": "user", "parts": [{"text": "hello"}]}
            },
        }
        async with client:
            resp = await client.post("/a2a", json=spec_body)
        assert resp.status_code == 200
        assert resp.json() == spec_body

    @pytest.mark.asyncio
    async def test_post_to_other_path_not_touched(
        self, client: AsyncClient
    ) -> None:
        po_body = {
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_USER"}},
        }
        async with client:
            resp = await client.post(
                "/.well-known/agent-card.json", json=po_body
            )
        assert resp.status_code == 200
        # Path not /a2a → middleware does not transform.
        assert resp.json()["method"] == "SendMessage"
        assert resp.json()["params"]["message"]["role"] == "ROLE_USER"

    @pytest.mark.asyncio
    async def test_get_to_a2a_not_touched(self, client: AsyncClient) -> None:
        async with client:
            resp = await client.get("/a2a")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "method": "GET"}

    @pytest.mark.asyncio
    async def test_malformed_json_passes_through(
        self, app: FastAPI
    ) -> None:
        """Non-JSON body reaches the handler verbatim — SDK returns its own error."""

        # Custom handler that captures the raw bytes so we can assert the
        # malformed body survived the middleware.
        captured: dict[str, bytes] = {}

        async def raw_echo(request: Request) -> JSONResponse:
            captured["body"] = await request.body()
            return JSONResponse({"ok": True})

        # Replace the existing /a2a POST route with one that captures raw bytes.
        for route in list(app.router.routes):
            if getattr(route, "path", None) == "/a2a" and "POST" in getattr(
                route, "methods", set()
            ):
                app.router.routes.remove(route)
        app.post("/a2a")(raw_echo)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post(
                "/a2a",
                content=b"this is not json {{{",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        assert captured["body"] == b"this is not json {{{"

    @pytest.mark.asyncio
    async def test_method_rewrite_emits_info_log(
        self, client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        po_body = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_USER", "parts": []}},
        }
        with caplog.at_level(logging.INFO, logger="vigil.a2a.po_compat"):
            async with client:
                resp = await client.post("/a2a", json=po_body)
        assert resp.status_code == 200
        method_log = [r for r in caplog.records if "rewrote method" in r.message]
        role_log = [r for r in caplog.records if "rewrote role" in r.message]
        assert method_log, "expected an INFO log on method rewrite"
        assert role_log, "expected an INFO log on role rewrite"
        # No PII / token leakage in the structured extras.
        for record in method_log + role_log:
            assert "ROLE_USER" not in record.message
            assert "Bearer" not in record.message

    @pytest.mark.asyncio
    async def test_empty_body_passes_through(self, app: FastAPI) -> None:
        """An empty POST body reaches the handler unchanged."""
        captured: dict[str, bytes] = {}

        async def raw_echo(request: Request) -> JSONResponse:
            captured["body"] = await request.body()
            return JSONResponse({"ok": True})

        for route in list(app.router.routes):
            if getattr(route, "path", None) == "/a2a" and "POST" in getattr(
                route, "methods", set()
            ):
                app.router.routes.remove(route)
        app.post("/a2a")(raw_echo)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post(
                "/a2a",
                content=b"",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        assert captured["body"] == b""

    @pytest.mark.asyncio
    async def test_non_dict_json_passes_through(
        self, client: AsyncClient
    ) -> None:
        """A JSON array (not a dict) reaches the handler verbatim."""
        async with client:
            resp = await client.post(
                "/a2a",
                json=[1, 2, 3],
                headers={"content-type": "application/json"},
            )
        # Echo handler returns whatever JSON body it parsed.
        assert resp.status_code == 200
        assert resp.json() == [1, 2, 3]
