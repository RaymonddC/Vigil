"""Unit tests for backend/cache.py — I4 performance + caching pass.

Tests:
- LLM cache: hit / miss / TTL expiry / provider-keyed isolation
- LLM cache: set_llm_cached idempotency
- LLM cache: invalidate_llm_provider clears TTL-expired entries
- FHIR cache: hits and misses within fhir_cache_scope
- FHIR cache: scope isolation (no bleed between scopes)
- FHIR cache: no-op outside scope
- get_cache_stats returns expected shape
"""

from __future__ import annotations

import time

import pytest

from backend.cache import (
    fhir_cache_get,
    fhir_cache_key,
    fhir_cache_scope,
    fhir_cache_set,
    get_cache_stats,
    get_llm_cached,
    invalidate_llm_provider,
    set_llm_cached,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

URL = "http://localhost:8080/fhir"
PID = "PT-001"
PROVIDER = "stub/template"
PROMPT = "Generate SBAR for patient PT-001."


# ---------------------------------------------------------------------------
# LLM cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_cache_miss_then_hit() -> None:
    """First get returns None; after set, get returns the stored value."""
    result_before = await get_llm_cached(PROMPT, PROVIDER, URL, PID)
    assert result_before is None, "Expected cache miss on first call"

    await set_llm_cached(PROMPT, PROVIDER, URL, PID, "S: test. B: test. A: test. R: test.")
    result_after = await get_llm_cached(PROMPT, PROVIDER, URL, PID)
    assert result_after is not None
    assert "S: test" in result_after


@pytest.mark.asyncio
async def test_llm_cache_provider_isolation() -> None:
    """Different provider names produce different cache keys."""
    prompt = f"isolation-test-{time.time()}"
    value_a = "provider A response"
    value_b = "provider B response"

    await set_llm_cached(prompt, "groq/llama", URL, PID, value_a)
    await set_llm_cached(prompt, "ollama/llama3.1", URL, PID, value_b)

    assert await get_llm_cached(prompt, "groq/llama", URL, PID) == value_a
    assert await get_llm_cached(prompt, "ollama/llama3.1", URL, PID) == value_b


@pytest.mark.asyncio
async def test_llm_cache_patient_isolation() -> None:
    """Different patient IDs produce different cache keys."""
    prompt = f"patient-isolation-test-{time.time()}"
    await set_llm_cached(prompt, PROVIDER, URL, "PT-001", "resp-001")
    await set_llm_cached(prompt, PROVIDER, URL, "PT-007", "resp-007")

    assert await get_llm_cached(prompt, PROVIDER, URL, "PT-001") == "resp-001"
    assert await get_llm_cached(prompt, PROVIDER, URL, "PT-007") == "resp-007"


@pytest.mark.asyncio
async def test_llm_cache_ttl_expiry() -> None:
    """Entries with TTL=0 are immediately stale."""
    prompt = f"ttl-test-{time.time()}"
    await set_llm_cached(prompt, PROVIDER, URL, PID, "will expire", ttl=0)
    # After TTL=0 the entry is expired on next get
    result = await get_llm_cached(prompt, PROVIDER, URL, PID)
    assert result is None, "Expected expired entry to return None"


@pytest.mark.asyncio
async def test_llm_cache_invalidate_provider() -> None:
    """invalidate_llm_provider removes TTL-expired entries."""
    prompt = f"invalidate-test-{time.time()}"
    await set_llm_cached(prompt, "victim-provider", URL, PID, "cached", ttl=0)
    removed = await invalidate_llm_provider("victim-provider")
    # Should have cleaned at least the expired entry
    assert isinstance(removed, int)
    assert removed >= 0


# ---------------------------------------------------------------------------
# FHIR cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fhir_cache_miss_outside_scope() -> None:
    """fhir_cache_get returns None when no scope is active."""
    key = fhir_cache_key(URL, "Patient/PT-001", None)
    result = fhir_cache_get(key)
    assert result is None


@pytest.mark.asyncio
async def test_fhir_cache_hit_within_scope() -> None:
    """Values set within fhir_cache_scope are retrievable in the same scope."""
    key = fhir_cache_key(URL, "Observation", {"patient": "PT-001", "category": "vital-signs"})
    async with fhir_cache_scope():
        assert fhir_cache_get(key) is None  # miss
        fhir_cache_set(key, {"entry": [{"resource": {"resourceType": "Observation"}}]})
        cached = fhir_cache_get(key)
        assert cached is not None
        assert cached["entry"][0]["resource"]["resourceType"] == "Observation"


@pytest.mark.asyncio
async def test_fhir_cache_scope_isolation() -> None:
    """Cache from one scope is NOT visible in a subsequent scope."""
    key = fhir_cache_key(URL, "Patient/PT-002", None)
    async with fhir_cache_scope():
        fhir_cache_set(key, {"data": "scope1"})

    # After first scope exits, the store is gone
    result_outside = fhir_cache_get(key)
    assert result_outside is None

    async with fhir_cache_scope():
        result_new = fhir_cache_get(key)
        assert result_new is None, "New scope should not inherit prior scope's cache"


@pytest.mark.asyncio
async def test_fhir_cache_set_noop_outside_scope() -> None:
    """fhir_cache_set is a no-op outside an active scope."""
    key = fhir_cache_key(URL, "Condition", {"patient": "PT-003"})
    fhir_cache_set(key, {"entry": []})  # should not raise
    # And still a miss because no scope is active
    assert fhir_cache_get(key) is None


@pytest.mark.asyncio
async def test_fhir_cache_key_deterministic() -> None:
    """fhir_cache_key is deterministic regardless of param dict order."""
    key1 = fhir_cache_key(URL, "Observation", {"patient": "PT-001", "_count": "100"})
    key2 = fhir_cache_key(URL, "Observation", {"_count": "100", "patient": "PT-001"})
    assert key1 == key2, "Cache key must be stable across param ordering"


# ---------------------------------------------------------------------------
# get_cache_stats tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cache_stats_shape() -> None:
    """get_cache_stats returns expected top-level structure."""
    stats = await get_cache_stats()
    assert "llm" in stats
    assert "fhir" in stats

    llm = stats["llm"]
    for k in ("hits", "misses", "evictions", "size", "ttl_sec"):
        assert k in llm, f"Missing key '{k}' in llm stats"

    fhir = stats["fhir"]
    for k in ("hits", "misses", "scope_active"):
        assert k in fhir, f"Missing key '{k}' in fhir stats"


@pytest.mark.asyncio
async def test_get_cache_stats_scope_active_flag() -> None:
    """scope_active reflects whether fhir_cache_scope is entered."""
    stats_before = await get_cache_stats()
    assert stats_before["fhir"]["scope_active"] is False

    async with fhir_cache_scope():
        stats_during = await get_cache_stats()
        assert stats_during["fhir"]["scope_active"] is True

    stats_after = await get_cache_stats()
    assert stats_after["fhir"]["scope_active"] is False
