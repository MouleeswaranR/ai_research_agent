"""Unified LLM client – routes to NVIDIA NIM (primary) or Groq (fallback).

Supports OpenAI-compatible payloads, thinking/reasoning parameters for NVIDIA NIM,
automatic provider fallback on 429/5xx errors, per-task best-model selection,
and automatic tracing of all LLM interactions for the dashboard.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx

from app.config import settings
from app.logging import get_logger
from app.token_tracker import TokenUsage, token_tracker

logger = get_logger("llm_client")


class NvidiaNimRateLimiter:
    """Token bucket rate limiter for NVIDIA NIM to respect the 40 RPM limit.

    Coordinates rate limiting across processes using Redis when available, falling back
    to an in-memory token bucket if Redis is not running or fails.
    """

    def __init__(self, rpm: int = 40) -> None:
        self.rpm = rpm
        self.max_tokens = float(rpm)
        self.refill_rate = rpm / 60.0  # tokens per second
        self.redis_url = settings.redis_url

        # Local fallback parameters
        self._local_tokens = float(self.max_tokens)
        self._local_last_update = time.time()
        self._lock = asyncio.Lock()

        # Redis client state
        self._redis_client = None
        self._redis_conn_failed = False
        self._redis_last_fail = 0.0

    async def _get_redis(self):
        """Lazy load the Redis client, handle connection failures and timeouts."""
        now = time.time()
        if self._redis_conn_failed and now - self._redis_last_fail > 60:
            # Retry Redis after 60 seconds
            self._redis_conn_failed = False
            self._redis_client = None

        if self._redis_conn_failed:
            return None

        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis
                self._redis_client = aioredis.from_url(
                    self.redis_url,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                    decode_responses=True,
                )
                await self._redis_client.ping()
            except Exception as e:
                logger.warning("redis_limiter_connection_failed", error=str(e))
                self._redis_conn_failed = True
                self._redis_last_fail = now
                self._redis_client = None

        return self._redis_client

    async def acquire(self) -> None:
        """Acquire a token, sleeping if necessary to comply with the rate limit."""
        while True:
            redis_client = await self._get_redis()
            if redis_client:
                try:
                    # Lua script to perform thread-safe rate limiting in Redis
                    # KEYS[1] = token key, KEYS[2] = last update timestamp key
                    # ARGV[1] = max_tokens, ARGV[2] = refill_rate (tokens/sec), ARGV[3] = current_time
                    lua_script = """
                    local tokens_key = KEYS[1]
                    local timestamp_key = KEYS[2]
                    
                    local max_tokens = tonumber(ARGV[1])
                    local refill_rate = tonumber(ARGV[2])
                    local current_time = tonumber(ARGV[3])
                    
                    local last_tokens = tonumber(redis.call('get', tokens_key))
                    local last_update = tonumber(redis.call('get', timestamp_key))
                    
                    if not last_tokens then
                        last_tokens = max_tokens
                        last_update = current_time
                    end
                    
                    local elapsed = current_time - last_update
                    local new_tokens = math.min(max_tokens, last_tokens + (elapsed * refill_rate))
                    
                    if new_tokens >= 1.0 then
                        redis.call('set', tokens_key, new_tokens - 1.0)
                        redis.call('set', timestamp_key, current_time)
                        return 1
                    else
                        local needed = 1.0 - new_tokens
                        local wait_time = needed / refill_rate
                        return wait_time * -1
                    end
                    """
                    now = time.time()
                    res = await redis_client.eval(
                        lua_script,
                        2,
                        "limiter:nvidia_nim:tokens",
                        "limiter:nvidia_nim:last_update",
                        self.max_tokens,
                        self.refill_rate,
                        now,
                    )

                    if res == 1:
                        return
                    else:
                        wait_time = -res
                        logger.info("rate_limiter_waiting_redis", wait_time=wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                except Exception as e:
                    logger.warning("redis_limiter_eval_error_falling_back", error=str(e))
                    self._redis_client = None
                    self._redis_conn_failed = True
                    self._redis_last_fail = time.time()

            # Local fallback (using asyncio lock)
            async with self._lock:
                now = time.time()
                elapsed = now - self._local_last_update
                self._local_tokens = min(self.max_tokens, self._local_tokens + (elapsed * self.refill_rate))
                self._local_last_update = now

                if self._local_tokens >= 1.0:
                    self._local_tokens -= 1.0
                    return
                else:
                    needed = 1.0 - self._local_tokens
                    wait_time = needed / self.refill_rate

            logger.info("rate_limiter_waiting_local", wait_time=wait_time)
            await asyncio.sleep(wait_time)


# Global rate limiter for NVIDIA NIM (40 requests per minute)
nvidia_nim_rate_limiter = NvidiaNimRateLimiter(rpm=40)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ── Per-provider, per-task-type best free models ─────────────────────────
# Keys: (provider, task_type) → model name
# task_type: "planning" | "coding" | "review" | "fast"
PROVIDER_TASK_MODELS: dict[tuple[str, str], str] = {
    # Gemini – all tasks use gemini-2.5-flash (generous free tier)
    ("gemini", "planning"): "gemini-2.5-flash",
    ("gemini", "coding"):   "gemini-2.5-flash",
    ("gemini", "review"):   "gemini-2.5-flash",
    ("gemini", "fast"):     "gemini-2.5-flash",

    # OpenRouter – verified working free tier models (2026-07-06)
    ("openrouter", "planning"): "nvidia/nemotron-3-ultra-550b-a55b:free",
    ("openrouter", "coding"):   "openai/gpt-oss-120b:free",
    ("openrouter", "review"):   "google/gemma-4-26b-a4b-it:free",
    ("openrouter", "fast"):     "google/gemma-4-26b-a4b-it:free",

    # Groq – fast inference, generous free tier
    ("groq", "planning"): "llama-3.3-70b-versatile",
    ("groq", "coding"):   "llama-3.3-70b-versatile",
    ("groq", "review"):   "llama-3.1-8b-instant",
    ("groq", "fast"):     "llama-3.1-8b-instant",

    # NVIDIA NIM
    ("nvidia_nim", "planning"): "nvidia/nemotron-3-ultra-550b-a55b",
    ("nvidia_nim", "coding"):   "moonshotai/kimi-k2.6",
    ("nvidia_nim", "review"):   "minimaxai/minimax-m3",
    ("nvidia_nim", "fast"):     "minimaxai/minimax-m3",
}

# Max output tokens per provider
PROVIDER_MAX_TOKENS: dict[str, int] = {
    "groq": 8192,
    "gemini": 16384,
    "openrouter": 15000,
    "nvidia_nim": 16384,
}


def _get_nim_url() -> str:
    """Build the NVIDIA NIM chat completions URL."""
    base = settings.nvidia_nim_base_url.rstrip("/")
    return f"{base}/chat/completions"


def _get_task_type(agent_name: str) -> str:
    """Map an agent name to a task type for model selection."""
    return settings.TASK_TYPE_MAP.get(agent_name, "fast")


def _get_best_model_for_provider(provider: str, agent_name: str, use_fast: bool = False) -> str:
    """Pick the best model for this provider + agent combination."""
    if use_fast:
        task_type = "fast"
    else:
        task_type = _get_task_type(agent_name)

    # Check the per-provider-task map first
    key = (provider, task_type)
    if key in PROVIDER_TASK_MODELS:
        return PROVIDER_TASK_MODELS[key]

    # Fallback to configured defaults
    if provider == "gemini":
        return settings.gemini_fast_model if use_fast else settings.gemini_model
    elif provider == "openrouter":
        return settings.openrouter_fast_model if use_fast else settings.openrouter_model
    elif provider == "nvidia_nim":
        default = settings.AGENT_MODEL_MAP.get(agent_name, settings.nvidia_nim_model)
        return settings.nvidia_nim_fast_model if use_fast else default
    else:  # groq
        return settings.groq_fast_model if use_fast else settings.groq_model


def _get_provider_config(
    agent_name: str = "unknown",
    model_override: str | None = None,
    use_fast: bool = False,
    force_provider: str | None = None,
) -> dict:
    """Return API URL, headers, and model for the active provider."""
    provider = force_provider or settings.llm_provider

    # 1. Google Gemini (AI Studio)
    if provider == "gemini" and settings.gemini_api_key:
        model = model_override or _get_best_model_for_provider("gemini", agent_name, use_fast)
        base = settings.gemini_base_url.rstrip("/")
        return {
            "provider": "gemini",
            "url": f"{base}/chat/completions",
            "headers": {
                "Authorization": f"Bearer {settings.gemini_api_key}",
                "Content-Type": "application/json",
            },
            "model": model,
        }

    # 2. OpenRouter
    if provider == "openrouter" and settings.openrouter_api_key:
        model = model_override or _get_best_model_for_provider("openrouter", agent_name, use_fast)
        base = settings.openrouter_base_url.rstrip("/")
        return {
            "provider": "openrouter",
            "url": f"{base}/chat/completions",
            "headers": {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/ai-software-builder-agent",
                "X-Title": "Auto Dev Agent",
            },
            "model": model,
        }

    # 3. NVIDIA NIM
    api_key = settings.nvidia_nim_api_key
    if provider == "nvidia_nim" and api_key and not api_key.startswith("your-"):
        model = model_override or _get_best_model_for_provider("nvidia_nim", agent_name, use_fast)
        return {
            "provider": "nvidia_nim",
            "url": _get_nim_url(),
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "model": model,
        }

    # 4. Fallback to Groq
    model = model_override or _get_best_model_for_provider("groq", agent_name, use_fast)
    return {
        "provider": "groq",
        "url": GROQ_API_URL,
        "headers": {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
        "model": model,
    }


def _record_trace(
    agent_name: str,
    provider: str,
    model: str,
    messages: list[dict],
    content: str,
    usage: dict,
    latency_ms: float,
    reasoning_content: str = "",
) -> None:
    """Record this LLM call in the active agent trace, if tracing is enabled."""
    if not settings.trace_enabled:
        return

    from app.tracing.tracer import pipeline_tracer

    trace = pipeline_tracer.get_active_trace(agent_name)
    if trace is None:
        return

    # Capture the prompts
    for msg in messages:
        if msg["role"] == "system" and not trace.system_prompt:
            trace.system_prompt = msg["content"]
        elif msg["role"] == "user" and not trace.user_prompt:
            trace.user_prompt = msg["content"]

    trace.llm_raw_response = content
    trace.model_used = model
    trace.provider = provider
    trace.token_usage = usage

    if reasoning_content:
        trace.add_step(
            "reasoning",
            reasoning_content,
            model=model,
            provider=provider,
        )

    trace.add_step(
        "llm_response",
        f"Model: {model} | Tokens: {usage.get('total_tokens', 0)} | Latency: {latency_ms:.0f}ms",
        model=model,
        provider=provider,
        latency_ms=latency_ms,
    )


def _build_payload(
    config: dict,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    response_format: dict | None,
    extra_body: dict | None,
) -> dict:
    """Build the request payload, respecting per-provider token limits."""
    effective_tokens = min(max_tokens, PROVIDER_MAX_TOKENS.get(config["provider"], 15000))

    payload: dict = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": effective_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    # NVIDIA NIM thinking/reasoning support
    if config["provider"] == "nvidia_nim":
        if extra_body:
            payload.update(extra_body)
        else:
            model_lower = config["model"].lower()
            if "nemotron" in model_lower:
                payload["chat_template_kwargs"] = {"enable_thinking": True}
                payload["reasoning_budget"] = 16384
            elif "glm" in model_lower:
                payload["chat_template_kwargs"] = {"enable_thinking": True, "clear_thinking": False}

    return payload


async def call_llm(
    messages: list[dict],
    *,
    agent_name: str = "unknown",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    response_format: dict | None = None,
    use_fast: bool = False,
    extra_body: dict | None = None,
) -> dict:
    """Call the active LLM provider with automatic multi-provider fallback.

    Fallback strategy:
    1. Try primary provider (up to 2 attempts with backoff)
    2. On 429/5xx/connection error → switch to next provider in fallback chain
    3. Continue through chain until success or all providers exhausted

    Returns: {"content": str, "usage": dict, "provider": str, "model": str}
    """
    fallback_chain = settings.fallback_chain
    if not fallback_chain:
        fallback_chain = [settings.llm_provider]

    start = time.perf_counter()
    last_error: Exception | None = None

    for provider_idx, provider_name in enumerate(fallback_chain):
        # Get config for this provider (no model override on fallback providers)
        if provider_idx == 0:
            config = _get_provider_config(
                agent_name=agent_name, model_override=model, use_fast=use_fast
            )
        else:
            # Fallback: pick best model for this provider + task, ignore original model override
            config = _get_provider_config(
                agent_name=agent_name, model_override=None, use_fast=use_fast,
                force_provider=provider_name,
            )
            logger.warning(
                "provider_fallback",
                agent=agent_name,
                from_provider=fallback_chain[provider_idx - 1],
                to_provider=provider_name,
                model=config["model"],
            )

        payload = _build_payload(config, messages, max_tokens, temperature, response_format, extra_body)

        # Try this provider up to 2 times (retry once on transient errors)
        max_retries_per_provider = 2
        for attempt in range(max_retries_per_provider):
            try:
                if config["provider"] == "nvidia_nim":
                    await nvidia_nim_rate_limiter.acquire()
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        config["url"], json=payload, headers=config["headers"]
                    )
            except Exception as e:
                logger.warning(
                    "llm_request_connection_error",
                    agent=agent_name,
                    provider=config["provider"],
                    attempt=attempt + 1,
                    error=str(e),
                )
                last_error = e
                if attempt < max_retries_per_provider - 1:
                    await asyncio.sleep(2)
                    continue
                break  # Move to next provider

            # ── Rate limited (429) ──
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt + 1)
                logger.warning(
                    "rate_limited",
                    agent=agent_name,
                    provider=config["provider"],
                    model=config["model"],
                    retry_in=wait,
                    attempt=attempt + 1,
                    will_fallback=attempt >= max_retries_per_provider - 1,
                )
                last_error = httpx.HTTPStatusError(
                    f"429 Too Many Requests from {config['provider']}",
                    request=response.request,
                    response=response,
                )
                if attempt < max_retries_per_provider - 1:
                    await asyncio.sleep(wait)
                    continue
                break  # Move to next provider

            # ── Server errors (5xx) ──
            if response.status_code in (500, 502, 503, 504):
                logger.warning(
                    "server_error",
                    agent=agent_name,
                    provider=config["provider"],
                    model=config["model"],
                    status_code=response.status_code,
                    error=response.text[:200],
                    attempt=attempt + 1,
                )
                last_error = httpx.HTTPStatusError(
                    f"{response.status_code} from {config['provider']}",
                    request=response.request,
                    response=response,
                )
                if attempt < max_retries_per_provider - 1:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                break  # Move to next provider

            # ── Client errors (400, 401, 403, 404) – don't retry, move to next provider ──
            if response.status_code in (400, 401, 403, 404):
                logger.warning(
                    "client_error_switching_provider",
                    agent=agent_name,
                    provider=config["provider"],
                    model=config["model"],
                    status_code=response.status_code,
                    error=response.text[:200],
                )
                last_error = httpx.HTTPStatusError(
                    f"{response.status_code} from {config['provider']}",
                    request=response.request,
                    response=response,
                )
                break  # Move to next provider immediately

            # ── Success ──
            response.raise_for_status()

            latency_ms = (time.perf_counter() - start) * 1000
            data = response.json()

            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning_content", "") or ""

            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Track usage globally
            token_usage_rec = TokenUsage(
                agent_name=agent_name,
                model=config["model"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
            )
            token_tracker.record(token_usage_rec)

            # Record trace
            _record_trace(
                agent_name=agent_name,
                provider=config["provider"],
                model=config["model"],
                messages=messages,
                content=content,
                usage={"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens},
                latency_ms=latency_ms,
                reasoning_content=reasoning,
            )

            if provider_idx > 0:
                logger.info(
                    "fallback_succeeded",
                    agent=agent_name,
                    provider=config["provider"],
                    model=config["model"],
                )

            return {
                "content": content,
                "reasoning": reasoning,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens},
                "provider": config["provider"],
                "model": config["model"],
            }
        # end retry loop — if we get here, this provider failed, continue to next
        continue

    # All providers exhausted
    logger.error(
        "all_providers_exhausted",
        agent=agent_name,
        providers_tried=[p for p in fallback_chain],
    )
    if last_error:
        raise last_error
    raise RuntimeError(f"All LLM providers exhausted for agent '{agent_name}': {fallback_chain}")


async def call_llm_json(
    messages: list[dict],
    *,
    agent_name: str = "unknown",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    use_fast: bool = False,
    extra_body: dict | None = None,
) -> dict:
    effective_max_tokens = max(max_tokens, 2048)
    response_format = {"type": "json_object"}

    result = await call_llm(
        messages=messages,
        agent_name=agent_name,
        model=model,
        max_tokens=effective_max_tokens,
        temperature=temperature,
        response_format=response_format,
        use_fast=use_fast,
        extra_body=extra_body,
    )

    raw_text = result["content"].strip()

    # Clean code fences if the model wrapped JSON in ```json ... ```
    if "```" in raw_text:
        lines = raw_text.splitlines()
        clean_lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(clean_lines).strip()

    # Try standard parse
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback: find first '{' and last '}'
        start_idx = raw_text.find("{")
        end_idx = raw_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            substring = raw_text[start_idx : end_idx + 1]
            try:
                return json.loads(substring)
            except json.JSONDecodeError:
                pass

        logger.warning(
            "json_parse_failed",
            agent=agent_name,
            content=raw_text[:200],
        )
        return {"raw_output": raw_text}
