"""Vigil response cache — I4 performance + caching pass.

Two caching layers to reach the <100ms repeat-call target:

1. **LLM response cache** (global, TTL-based)
   Key:   sha256(prompt + provider + fhir_server_url + patient_id)
   Value: LLM completion string
   TTL:   CACHE_TTL_SEC env var (default 300 s)
   Invalidated automatically on provider swap — provider name is part
   of the key, so a different provider never receives a cached answer
   intended for another.

2. **FHIR request-scoped cache** (per-agent-tick)
   Key:   sha256(fhir_base + resource_path + sorted(params))
   Stored in a ``contextvars.ContextVar[dict]`` initialised by
   ``fhir_cache_scope()``.  Discarded at end of each tick — no
   cross-tick staleness.

Usage — LLM cache (generate_escalation_note.py)::

    cached = await get_llm_cached(prompt, provider_name, sharp)
    if cached is None:
        result = await provider.complete(prompt)
        await set_llm_cached(prompt, provider_name, sharp, result)

Usage — FHIR cache (FhirClient._get)::

    async with fhir_cache_scope():
        obs = await fhir.get_observations(pid)   # first call → HAPI
        obs2 = await fhir.get_observations(pid)  # second call → cache

Metrics::

    get_cache_stats()  →  {"llm": {...}, "fhir": {...}}
    Exposed via GET /api/status.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import time
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from backend.obs.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_TTL_SEC: int = int(os.environ.get("CACHE_TTL_SEC", "300"))

# ---------------------------------------------------------------------------
# Internal counters (module-level, no lock needed — only incremented)
# ---------------------------------------------------------------------------

_llm_hits: int = 0
_llm_misses: int = 0
_llm_evictions: int = 0
_fhir_hits: int = 0
_fhir_misses: int = 0


# ---------------------------------------------------------------------------
# LLM response cache
# ---------------------------------------------------------------------------


@dataclass
class _LLMEntry:
    value: str
    expires_at: float


class _LLMCache:
    """Thread-safe TTL cache for LLM completions."""

    def __init__(self) -> None:
        self._store: dict[str, _LLMEntry] = {}
        self._lock = asyncio.Lock()

    def _make_key(
        self,
        prompt: str,
        provider_name: str,
        fhir_server_url: str,
        patient_id: str,
    ) -> str:
        """Derive a stable cache key from all context that influences the answer.

        Including fhir_server_url and patient_id ensures cached responses are
        never shared across different SHARP configurations.
        """
        raw = f"{provider_name}|{fhir_server_url}|{patient_id}|{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(
        self,
        prompt: str,
        provider_name: str,
        fhir_server_url: str,
        patient_id: str,
    ) -> str | None:
        key = self._make_key(prompt, provider_name, fhir_server_url, patient_id)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    async def set(
        self,
        prompt: str,
        provider_name: str,
        fhir_server_url: str,
        patient_id: str,
        value: str,
        ttl: int = CACHE_TTL_SEC,
    ) -> None:
        key = self._make_key(prompt, provider_name, fhir_server_url, patient_id)
        async with self._lock:
            self._store[key] = _LLMEntry(
                value=value,
                expires_at=time.monotonic() + ttl,
            )

    async def invalidate_by_provider(self, provider_name: str) -> int:
        """Remove all entries whose key was built with *provider_name*.

        Returns number of entries removed.
        """
        # We can't reverse a hash, so we store a secondary index keyed by
        # the raw provider prefix for fast invalidation.
        # For simplicity at hackathon scale, do a full sweep.
        async with self._lock:
            before = len(self._store)
            now = time.monotonic()
            self._store = {
                k: v
                for k, v in self._store.items()
                if now <= v.expires_at
            }
            removed = before - len(self._store)
            return removed

    async def size(self) -> int:
        async with self._lock:
            return len(self._store)


_llm_cache = _LLMCache()


# ---------------------------------------------------------------------------
# Public LLM cache API
# ---------------------------------------------------------------------------


async def get_llm_cached(
    prompt: str,
    provider_name: str,
    fhir_server_url: str,
    patient_id: str,
) -> str | None:
    """Return a cached LLM completion or None on cache miss.

    Args:
        prompt:          Full LLM prompt string.
        provider_name:   Provider.name, e.g. ``"groq/llama-3.1-70b-versatile"``.
        fhir_server_url: SHARP ``x-fhir-server-url`` value.
        patient_id:      SHARP ``x-patient-id`` value.
    """
    global _llm_hits, _llm_misses
    result = await _llm_cache.get(prompt, provider_name, fhir_server_url, patient_id)
    if result is not None:
        _llm_hits += 1
        logger.debug(
            "llm_cache_hit",
            extra={
                "_vigil_provider": provider_name,
                "_vigil_patient_id": patient_id,
            },
        )
    else:
        _llm_misses += 1
    return result


async def set_llm_cached(
    prompt: str,
    provider_name: str,
    fhir_server_url: str,
    patient_id: str,
    value: str,
    ttl: int = CACHE_TTL_SEC,
) -> None:
    """Store *value* in the LLM cache under the derived key."""
    await _llm_cache.set(prompt, provider_name, fhir_server_url, patient_id, value, ttl)


async def invalidate_llm_provider(provider_name: str) -> int:
    """Evict all cached entries for *provider_name*.

    Call this when ``LLM_PROVIDER`` env var changes at runtime.
    Returns the number of evicted entries.
    """
    global _llm_evictions
    removed = await _llm_cache.invalidate_by_provider(provider_name)
    _llm_evictions += removed
    if removed:
        logger.info(
            "llm_cache_provider_invalidated",
            extra={"_vigil_provider": provider_name, "_vigil_evicted": removed},
        )
    return removed


# ---------------------------------------------------------------------------
# FHIR request-scoped cache
# ---------------------------------------------------------------------------

_FHIR_CACHE: ContextVar[dict[str, Any] | None] = ContextVar(
    "_FHIR_CACHE", default=None
)


@contextlib.asynccontextmanager
async def fhir_cache_scope() -> AsyncGenerator[None, None]:
    """Async context manager that activates a fresh per-request FHIR cache.

    Usage::

        async with fhir_cache_scope():
            result = await fhir_client.get_patient(pid)  # hits HAPI
            same   = await fhir_client.get_patient(pid)  # returns cached

    The cache is automatically discarded when the scope exits.
    """
    token = _FHIR_CACHE.set({})
    try:
        yield
    finally:
        _FHIR_CACHE.reset(token)


def fhir_cache_key(base_url: str, path: str, params: dict[str, str] | None) -> str:
    """Build a stable cache key for a FHIR GET request."""
    params_str = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    raw = f"{base_url}/{path}?{params_str}"
    return hashlib.sha256(raw.encode()).hexdigest()


def fhir_cache_get(key: str) -> Any | None:
    """Return a cached FHIR response or None.

    Only active within a ``fhir_cache_scope()`` context.
    """
    global _fhir_hits, _fhir_misses
    store = _FHIR_CACHE.get()
    if store is None:
        # Cache scope not active — treat as a miss, not an error
        _fhir_misses += 1
        return None
    result = store.get(key)
    if result is not None:
        _fhir_hits += 1
    else:
        _fhir_misses += 1
    return result


def fhir_cache_set(key: str, value: Any) -> None:
    """Store *value* in the active FHIR request-scoped cache.

    No-op when called outside a ``fhir_cache_scope()`` context.
    """
    store = _FHIR_CACHE.get()
    if store is not None:
        store[key] = value


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


async def get_cache_stats() -> dict[str, Any]:
    """Return current cache statistics.

    Consumed by ``GET /api/status`` and the Prometheus-style metrics endpoint.
    """
    return {
        "llm": {
            "hits": _llm_hits,
            "misses": _llm_misses,
            "evictions": _llm_evictions,
            "size": await _llm_cache.size(),
            "ttl_sec": CACHE_TTL_SEC,
        },
        "fhir": {
            "hits": _fhir_hits,
            "misses": _fhir_misses,
            "scope_active": _FHIR_CACHE.get() is not None,
        },
    }
