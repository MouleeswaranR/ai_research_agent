"""Token tracker – measures and logs token usage per LLM call."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.logging import get_logger

logger = get_logger("token_tracker")

# Pricing per 1M tokens (approximate)
PRICING = {
    # NVIDIA NIM models
    "meta/llama-3.3-70b-instruct": {"input": 0.54, "output": 0.54},
    "meta/llama-3.1-8b-instruct": {"input": 0.10, "output": 0.10},
    # Groq models
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
}
DEFAULT_PRICING = {"input": 0.50, "output": 0.50}


@dataclass
class TokenUsage:
    """Single LLM call usage record."""

    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    timestamp: float = field(default_factory=time.time)

    @property
    def cost_estimate_usd(self) -> float:
        """Estimate cost based on model-specific pricing."""
        pricing = PRICING.get(self.model, DEFAULT_PRICING)
        input_cost = (self.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)


class TokenTracker:
    """Accumulates token usage across the pipeline run."""

    def __init__(self) -> None:
        self._records: list[TokenUsage] = []

    def reset(self) -> None:
        """Clear all records for a fresh pipeline run."""
        self._records = []

    def record(self, usage: TokenUsage) -> None:
        """Log and store a usage record."""
        logger.info(
            "llm_call",
            agent=usage.agent_name,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=round(usage.latency_ms, 1),
            cost_usd=usage.cost_estimate_usd,
        )
        self._records.append(usage)

    @property
    def total_input_tokens(self) -> int:
        """Return total input tokens across all calls."""
        return sum(r.input_tokens for r in self._records)

    @property
    def total_output_tokens(self) -> int:
        """Return total output tokens across all calls."""
        return sum(r.output_tokens for r in self._records)

    @property
    def total_cost_usd(self) -> float:
        """Return total estimated cost across all calls."""
        return round(sum(r.cost_estimate_usd for r in self._records), 6)

    @property
    def records(self) -> list[TokenUsage]:
        """Return a copy of all recorded usages."""
        return list(self._records)

    def summary(self) -> dict:
        """Return aggregate summary suitable for API/dashboard display."""
        return {
            "total_calls": len(self._records),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "per_agent": self._per_agent_summary(),
        }

    def _per_agent_summary(self) -> dict:
        """Aggregate usage grouped by agent name."""
        agents: dict[str, dict] = {}
        for record in self._records:
            if record.agent_name not in agents:
                agents[record.agent_name] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            entry = agents[record.agent_name]
            entry["calls"] += 1
            entry["input_tokens"] += record.input_tokens
            entry["output_tokens"] += record.output_tokens
            entry["cost_usd"] = round(
                entry["cost_usd"] + record.cost_estimate_usd, 6
            )
        return agents


# Global tracker – one per process; call reset() per pipeline run if needed
token_tracker = TokenTracker()
