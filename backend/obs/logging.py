"""Structured JSON logging for Vigil.

Provides:
- JSON formatter for stdlib logging
- Request ID context variable (propagated across MCP + A2A calls)
- Bearer token redaction filter (SEC-03)
- get_logger() convenience wrapper

Call configure_logging() once at application startup. After that, any module
can call get_logger(__name__) without further setup.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

# ---------------------------------------------------------------------------
# Request ID — propagates across async tasks via ContextVar
# ---------------------------------------------------------------------------

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request ID, generating a short UUID if not set."""
    rid = request_id_var.get("")
    if not rid:
        rid = str(uuid.uuid4())[:8]
        request_id_var.set(rid)
    return rid


def set_request_id(rid: str) -> None:
    """Set the request ID for the current async context."""
    request_id_var.set(rid)


# ---------------------------------------------------------------------------
# Bearer token redaction (SEC-03)
# ---------------------------------------------------------------------------

# Matches "Bearer <token>" patterns; JWT parts and opaque tokens are 8+ chars
_TOKEN_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9+/._\-=]{8,}")


def redact_bearer_tokens(text: str) -> str:
    """Replace bearer tokens in *text* with [REDACTED].

    Used both by the log filter and by any code that needs to sanitise
    strings before passing them to external systems.
    """
    return _TOKEN_RE.sub(r"\1[REDACTED]", text)


class _BearerTokenFilter(logging.Filter):
    """Strips bearer tokens from log record message and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_bearer_tokens(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_bearer_tokens(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(redact_bearer_tokens(str(a)) for a in record.args)
        return True


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Formats log records as newline-delimited JSON objects.

    Extra fields injected via ``extra={"_vigil_<key>": value}`` in the
    logger call are unpacked into the top-level JSON object with the
    ``_vigil_`` prefix stripped.
    """

    _SKIP = frozenset(
        logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
    ) | {"message", "asctime"}

    @staticmethod
    def _safe_get_message(record: logging.LogRecord) -> str:
        """Get formatted message, falling back to raw msg on format errors.

        Third-party loggers (e.g. httpx) may pass %d format codes with
        string arguments, causing TypeError. Fall back to str(record.msg)
        to avoid crashing the formatter.
        """
        try:
            return record.getMessage()
        except Exception:
            return str(record.msg)

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
            "msg": self._safe_get_message(record),
        }
        # Unpack _vigil_* extras
        for key, value in record.__dict__.items():
            if key.startswith("_vigil_"):
                obj[key[7:]] = value
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, default=str)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def configure_logging(level: str = "INFO") -> None:
    """Wire JSON formatter + redaction filter onto the root logger.

    Idempotent — safe to call multiple times (only adds handlers once).
    """
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_BearerTokenFilter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Return a named logger pre-configured by configure_logging()."""
    return logging.getLogger(name)
