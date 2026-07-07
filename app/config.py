"""Auto Dev Company – Pydantic Settings loaded from .env."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration – all values come from environment variables."""

    # ── Graph Pipeline Feature Flag ───────────────────────────
    ENABLE_GRAPH_PIPELINE: bool = Field(False, description="Enable graph-based Phase 1 & 2 pipeline")

    # ── LLM Provider ─────────────────────────────────────────
    llm_provider: str = Field("nvidia_nim", description="Primary LLM: 'nvidia_nim', 'groq', 'gemini', or 'openrouter'")
    fallback_providers: str = Field(
        "openrouter,groq,nvidia_nim",
        description="Comma-separated fallback provider chain (tried in order when primary fails)",
    )

    # ── NVIDIA NIM ───────────────────────────────────────────
    nvidia_nim_api_key: str = Field("", description="NVIDIA NIM API key")
    nvidia_nim_base_url: str = Field(
        "https://integrate.api.nvidia.com/v1",
        description="NVIDIA NIM base URL",
    )
    nvidia_nim_model: str = Field(
        "moonshotai/kimi-k2.6",
        description="Primary NIM model",
    )
    nvidia_nim_fast_model: str = Field(
        "minimaxai/minimax-m3",
        description="Fast/cheap NIM model",
    )

    # ── Google Gemini (AI Studio) ─────────────────────────────
    gemini_api_key: str = Field("", description="Google Gemini API key")
    gemini_base_url: str = Field(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        description="Google Gemini OpenAI-compatible base URL",
    )
    gemini_model: str = Field(
        "gemini-2.5-flash",
        description="Primary Gemini model (e.g. gemini-2.5-flash, gemini-2.0-flash, gemini-1.5-pro)",
    )
    gemini_fast_model: str = Field(
        "gemini-2.5-flash",
        description="Fast Gemini model",
    )

    # ── OpenRouter ───────────────────────────────────────────
    openrouter_api_key: str = Field("", description="OpenRouter API key")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        description="OpenRouter base URL",
    )
    openrouter_model: str = Field(
        "deepseek/deepseek-r1:free",
        description="Primary OpenRouter model (e.g. deepseek/deepseek-r1:free, google/gemini-2.0-flash-exp:free, qwen/qwen-2.5-coder-32b-instruct:free)",
    )
    openrouter_fast_model: str = Field(
        "google/gemini-2.0-flash-exp:free",
        description="Fast OpenRouter model",
    )

    # ── Groq LLM ─────────────────────────────────────────────
    groq_api_key: str = Field("", description="Groq API key")
    groq_model: str = Field("llama-3.3-70b-versatile", description="Primary Groq model")
    groq_fast_model: str = Field("llama-3.1-8b-instant", description="Fast Groq model")

    # ── Neon DB ──────────────────────────────────────────────
    database_url: str = Field(..., description="Neon PostgreSQL connection string")

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0", description="Redis URL")

    # ── Celery ───────────────────────────────────────────────
    celery_broker_url: str = Field("redis://localhost:6379/1")
    celery_result_backend: str = Field("redis://localhost:6379/2")

    # ── Sandbox ──────────────────────────────────────────────
    sandbox_timeout: int = Field(60, description="Max seconds per sandbox command")
    sandbox_memory_limit: str = Field("512m")
    sandbox_cpu_limit: float = Field(1.0)
    sandbox_network_disabled: bool = Field(True)

    # ── Review Gate ──────────────────────────────────────────
    review_max_retries: int = Field(3)
    coverage_threshold: int = Field(85)
    complexity_threshold: int = Field(10)
    security_severity_block: str = Field("high")

    # ── Tracing ──────────────────────────────────────────────
    trace_enabled: bool = Field(True, description="Enable agent thinking trace")
    trace_save_to_disk: bool = Field(True, description="Save traces to output dir")

    # ── Logging ──────────────────────────────────────────────
    log_level: str = Field("INFO")
    log_format: str = Field("json")

    # ── Server ───────────────────────────────────────────────
    host: str = Field("0.0.0.0")
    port: int = Field(8000)

    @property
    def async_database_url(self) -> str:
        """Return database URL formatted for asyncpg."""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def active_model(self) -> str:
        """Return the active primary model name based on provider setting."""
        if self.llm_provider == "nvidia_nim":
            return self.nvidia_nim_model
        elif self.llm_provider == "gemini":
            return self.gemini_model
        elif self.llm_provider == "openrouter":
            return self.openrouter_model
        return self.groq_model

    @property
    def active_fast_model(self) -> str:
        """Return the active fast model name based on provider setting."""
        if self.llm_provider == "nvidia_nim":
            return self.nvidia_nim_fast_model
        elif self.llm_provider == "gemini":
            return self.gemini_fast_model
        elif self.llm_provider == "openrouter":
            return self.openrouter_fast_model
        return self.groq_fast_model

    @property
    def AGENT_MODEL_MAP(self) -> dict[str, str]:
        """Per-agent NVIDIA NIM model map."""
        return {
            "product_strategist": os.getenv("NIM_MODEL_PRODUCT_STRATEGIST", "nvidia/nemotron-3-ultra-550b-a55b"),
            "project_manager": os.getenv("NIM_MODEL_PROJECT_MANAGER", "nvidia/nemotron-3-ultra-550b-a55b"),
            "system_architect": os.getenv("NIM_MODEL_SYSTEM_ARCHITECT", "nvidia/nemotron-3-ultra-550b-a55b"),
            "security_architect": os.getenv("NIM_MODEL_SECURITY_ARCHITECT", "nvidia/nemotron-3-ultra-550b-a55b"),
            "planner": os.getenv("NIM_MODEL_PLANNER", "nvidia/nemotron-3-ultra-550b-a55b"),
            "code_generator": os.getenv("NIM_MODEL_CODE_GENERATOR", "moonshotai/kimi-k2.6"),
            "code_generator_escalation": os.getenv("NIM_MODEL_CODE_GENERATOR_ESCALATION", "nvidia/nemotron-3-ultra-550b-a55b"),
            "critique": os.getenv("NIM_MODEL_CRITIQUE", "minimaxai/minimax-m3"),
            "critique_escalation": os.getenv("NIM_MODEL_CRITIQUE_ESCALATION", "nvidia/nemotron-3-ultra-550b-a55b"),
            "self_eval": os.getenv("NIM_MODEL_SELF_EVAL", "minimaxai/minimax-m3"),
            "test_writer": os.getenv("NIM_MODEL_TEST_WRITER", "moonshotai/kimi-k2.6"),
            "refactor": os.getenv("NIM_MODEL_REFACTOR", "moonshotai/kimi-k2.6"),
            "deployment": os.getenv("NIM_MODEL_DEPLOYMENT", "minimaxai/minimax-m3"),
            "monitoring": os.getenv("NIM_MODEL_MONITORING", "minimaxai/minimax-m3"),
            "quality_evaluator": os.getenv("NIM_MODEL_QUALITY_EVALUATOR", "minimaxai/minimax-m3"),
        }

    # Agent name → task type for smart model selection during fallback
    TASK_TYPE_MAP: dict[str, str] = {
        "product_strategist": "planning",
        "project_manager": "planning",
        "system_architect": "planning",
        "security_architect": "planning",
        "planner": "planning",
        "code_generator": "coding",
        "refactor": "coding",
        "critique": "review",
        "self_eval": "review",
        "quality_evaluator": "review",
        "test_writer": "coding",
        "deployment": "fast",
        "monitoring": "fast",
    }

    @property
    def fallback_chain(self) -> list[str]:
        """Return ordered list of providers to try: primary first, then fallbacks.

        Providers without valid API keys are excluded.
        """
        primary = self.llm_provider
        fallbacks = [p.strip() for p in self.fallback_providers.split(",") if p.strip()]

        # Build ordered list: primary first, then fallbacks (deduplicated)
        chain = [primary]
        for p in fallbacks:
            if p not in chain:
                chain.append(p)

        # Filter to providers that have API keys configured
        available = []
        for p in chain:
            if p == "gemini" and self.gemini_api_key:
                available.append(p)
            elif p == "openrouter" and self.openrouter_api_key:
                available.append(p)
            elif p == "groq" and self.groq_api_key:
                available.append(p)
            elif p == "nvidia_nim" and self.nvidia_nim_api_key and not self.nvidia_nim_api_key.startswith("your-"):
                available.append(p)
        return available

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton – import this everywhere
settings = Settings()
