"""A2A v1 agent-card field overrides.

The installed ``a2a-sdk`` is on the v0.3 schema. Two of the v1 wire-form
fields don't round-trip through the parent classes' typed Pydantic
fields, and Prompt Opinion's ``Add Connection → Check`` rejects v0.3
cards (per the host's submission walkthrough). We adopt the same escape
hatch the reference does: subclass and override the field types so that
the v1 nested shapes pass straight through ``model_validate`` →
``model_dump(by_alias=True, exclude_none=True)``.

Specifically this preserves on the wire:

* ``securitySchemes.apiKey.apiKeySecurityScheme`` — the v1 nested form
  (with ``location`` rather than ``in``). The parent's discriminated
  union ``SecurityScheme`` would silently misvalidate the nested form as
  ``MutualTLSSecurityScheme`` because mTLS has no required fields.
* ``supportedInterfaces`` — including the v1 ``protocolBinding`` and
  ``protocolVersion`` keys. The parent only models
  ``additionalInterfaces`` with ``{transport, url}``; extra keys are
  silently dropped on the way out.
* ``capabilities.extensions[].params`` — already present on the parent
  in this SDK version, but mirrored here as defensive insurance and to
  match the reference shape.

When ``a2a-sdk`` ships native v1 support (an ``AgentCardV1`` class with
the matching shapes), drop this module and the import in ``app.py``.

Pattern: ``prompt-opinion/po-adk-python/shared/app_factory.py``.
"""

from __future__ import annotations

from typing import Any

from a2a.types import AgentCard, AgentExtension
from pydantic import Field


class AgentExtensionV1(AgentExtension):
    """Mirror the reference's per-extension override.

    ``params`` already exists on the v0.3 ``AgentExtension`` in this SDK
    version, but we restate it here so that future SDK bumps which
    tighten the field type don't silently drop our SMART scope payload.
    """

    params: dict[str, Any] | None = Field(default=None)


class AgentCardV1(AgentCard):
    """Override the two v0.3 fields that block the v1 wire form.

    Both attributes are typed as raw containers so that the nested v1
    payloads pass straight through pydantic without being re-routed
    through the parent's strict discriminated unions.
    """

    supportedInterfaces: list[dict[str, Any]] = Field(default_factory=list)
    securitySchemes: dict[str, Any] | None = None
