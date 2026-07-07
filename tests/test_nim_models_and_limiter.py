import time
from unittest.mock import patch

import pytest

from app.agents.llm_client import (
    PROVIDER_MAX_TOKENS,
    PROVIDER_TASK_MODELS,
    NvidiaNimRateLimiter,
    _build_payload,
)


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_acquires_tokens():
    """Verify that NvidiaNimRateLimiter can acquire tokens and enforces delay under rate limit."""
    # Create limiter with high rate to test quick acquisition
    limiter = NvidiaNimRateLimiter(rpm=600)  # 10 tokens per second

    with patch.object(limiter, "_get_redis", return_value=None):
        start = time.perf_counter()
        # Acquire 3 tokens immediately
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1  # should be virtually instant


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_rate_limits():
    """Verify that NvidiaNimRateLimiter enforces delay when token budget is exhausted."""
    # Use low RPM to make the delay measurable
    limiter = NvidiaNimRateLimiter(rpm=2)  # 2 RPM = 1 token every 30 seconds
    limiter.max_tokens = 1.0  # limit bucket to 1 token max
    limiter._local_tokens = 1.0

    with patch.object(limiter, "_get_redis", return_value=None):
        # Acquire the only available token
        await limiter.acquire()

        # The next acquire must wait for refill. Refill is 1 token per 30 seconds.
        # To avoid sitting in tests, let's patch time.time or refilling rate.
        # Instead of waiting 30 seconds, we check that it sleeps.
        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)
            # Advance internal limiter state so it succeeds on retry
            limiter._local_tokens = 1.0

        with patch("asyncio.sleep", mock_sleep):
            await limiter.acquire()

        assert len(sleep_calls) >= 1
        assert sleep_calls[0] > 0.0


@pytest.mark.asyncio
async def test_rate_limiter_redis_fallback():
    """Verify that if Redis connection fails, the limiter falls back to in-memory mode."""
    limiter = NvidiaNimRateLimiter(rpm=60)
    limiter.redis_url = "redis://nonexistent-host:6379"

    # We expect get_redis to return None and mark connection failed
    redis_client = await limiter._get_redis()
    assert redis_client is None
    assert limiter._redis_conn_failed is True

    # Try acquiring, it should proceed using local fallback without throwing exceptions
    start = time.perf_counter()
    await limiter.acquire()
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1


def test_build_payload_nemotron_reasoning():
    """Verify that _build_payload injects reasoning parameters for Nemotron models."""
    config = {
        "provider": "nvidia_nim",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
    }
    messages = [{"role": "user", "content": "Hello"}]

    payload = _build_payload(
        config=config,
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
        response_format=None,
        extra_body=None,
    )

    assert "chat_template_kwargs" in payload
    assert payload["chat_template_kwargs"]["enable_thinking"] is True
    assert payload["reasoning_budget"] == 16384


def test_build_payload_non_reasoning_model():
    """Verify that other models do not get reasoning parameters injected by default."""
    config = {
        "provider": "nvidia_nim",
        "model": "moonshotai/kimi-k2.6",
    }
    messages = [{"role": "user", "content": "Hello"}]

    payload = _build_payload(
        config=config,
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
        response_format=None,
        extra_body=None,
    )

    assert "chat_template_kwargs" not in payload
    assert "reasoning_budget" not in payload


def test_nim_model_configurations():
    """Verify task model mappings and token configuration values."""
    assert PROVIDER_TASK_MODELS[("nvidia_nim", "planning")] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert PROVIDER_TASK_MODELS[("nvidia_nim", "coding")] == "moonshotai/kimi-k2.6"
    assert PROVIDER_TASK_MODELS[("nvidia_nim", "review")] == "minimaxai/minimax-m3"
    assert PROVIDER_TASK_MODELS[("nvidia_nim", "fast")] == "minimaxai/minimax-m3"

    assert PROVIDER_MAX_TOKENS["nvidia_nim"] == 16384
