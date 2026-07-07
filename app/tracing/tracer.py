"""Trace collector for agent executions – powers the real-time thinking trace view."""

from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.logging import get_logger

logger = get_logger("tracer")


def _notify_dashboard(event: dict) -> None:
    """Send live event to local Web Dashboard server endpoint asynchronously."""
    try:
        data = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:8000/api/dashboard/broadcast",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        pass


@dataclass
class ThinkingStep:
    """A single reasoning / thinking step recorded during an agent's run."""

    step_type: str
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentTrace:
    """Complete trace record for one agent execution."""

    agent_name: str
    stage: str = ""
    attempt: int = 1
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration_ms: float = 0
    system_prompt: str = ""
    user_prompt: str = ""
    llm_raw_response: str = ""
    parsed_output: Any = None
    decision: str = ""
    thinking_steps: list[ThinkingStep] = field(default_factory=list)
    token_usage: dict = field(default_factory=dict)
    model_used: str = ""
    provider: str = ""
    success: bool = True
    error: str | None = None

    def add_step(self, step_type: str, content: str, **metadata) -> None:
        """Append a thinking step to this trace."""
        step = ThinkingStep(step_type=step_type, content=content, metadata=metadata)
        self.thinking_steps.append(step)

    def finish(self) -> None:
        """Mark this trace as finished and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 1)

    def to_dict(self) -> dict:
        """Serialize trace to JSON-compatible dict."""
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "stage": self.stage,
            "attempt": self.attempt,
            "start_time": datetime.fromtimestamp(
                self.start_time, tz=timezone.utc
            ).isoformat(),
            "end_time": (
                datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat()
                if self.end_time
                else None
            ),
            "duration_ms": self.duration_ms,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "llm_raw_response": self.llm_raw_response[:2000],
            "parsed_output": self.parsed_output,
            "decision": self.decision,
            "thinking_steps": [
                {
                    "step_type": s.step_type,
                    "content": s.content[:1000],
                    "timestamp": s.timestamp,
                    "metadata": s.metadata,
                }
                for s in self.thinking_steps
            ],
            "token_usage": self.token_usage,
            "model_used": self.model_used,
            "provider": self.provider,
            "success": self.success,
            "error": self.error,
        }


class PipelineTracer:
    """Collects all agent traces for a single pipeline run."""

    def __init__(self) -> None:
        self._traces: list[AgentTrace] = []
        self._active_traces: dict[str, AgentTrace] = {}
        self._pipeline_id: str = ""
        self._pipeline_start: float = 0

    def reset(self, pipeline_id: str = "") -> None:
        """Clear all traces and start fresh for a new pipeline run."""
        self._traces = []
        self._active_traces = {}
        self._pipeline_id = pipeline_id or str(uuid.uuid4())[:8]
        self._pipeline_start = time.time()
        _notify_dashboard({"type": "pipeline_started", "pipeline_id": self._pipeline_id})

    def start_trace(self, agent_name: str, stage: str = "", attempt: int = 1) -> AgentTrace:
        """Begin tracing a new agent execution."""
        trace = AgentTrace(agent_name=agent_name, stage=stage, attempt=attempt)
        self._active_traces[agent_name] = trace
        logger.info(
            "trace_started",
            trace_id=trace.trace_id,
            agent=agent_name,
            stage=stage,
        )
        _notify_dashboard({
            "type": "agent_started",
            "agent": agent_name,
            "stage": stage,
            "attempt": attempt,
        })
        return trace

    def end_trace(self, agent_name: str, success: bool = True, error: str | None = None) -> AgentTrace | None:
        """Complete an active trace and move it to the finished list."""
        trace = self._active_traces.pop(agent_name, None)
        if trace is None:
            return None

        trace.success = success
        trace.error = error
        trace.finish()
        self._traces.append(trace)

        logger.info(
            "trace_completed",
            trace_id=trace.trace_id,
            agent=agent_name,
            duration_ms=trace.duration_ms,
            success=success,
        )
        _notify_dashboard({
            "type": "agent_completed",
            "agent": agent_name,
            "content_length": len(trace.llm_raw_response),
            "duration_ms": trace.duration_ms,
            "trace": trace.to_dict(),
        })
        return trace

    def get_active_trace(self, agent_name: str) -> AgentTrace | None:
        """Return the currently active trace for an agent."""
        return self._active_traces.get(agent_name)

    @property
    def all_traces(self) -> list[AgentTrace]:
        """Return all completed traces."""
        return list(self._traces)

    def get_traces_for_agent(self, agent_name: str) -> list[AgentTrace]:
        """Return all completed traces for a specific agent."""
        return [t for t in self._traces if t.agent_name == agent_name]

    def get_traces_for_stage(self, stage: str) -> list[AgentTrace]:
        """Return all completed traces for a specific pipeline stage."""
        return [t for t in self._traces if t.stage == stage]

    def export_json(self) -> dict:
        """Export the entire pipeline trace as a JSON-compatible dictionary."""
        elapsed = round((time.time() - self._pipeline_start) * 1000, 1) if self._pipeline_start else 0
        return {
            "pipeline_id": self._pipeline_id,
            "total_traces": len(self._traces),
            "total_duration_ms": elapsed,
            "traces": [t.to_dict() for t in self._traces],
            "active_agents": list(self._active_traces.keys()),
        }

    def save_to_disk(self, output_dir: str) -> str:
        """Write the full trace to a JSON file on disk."""
        traces_dir = os.path.join(output_dir, "traces")
        os.makedirs(traces_dir, exist_ok=True)

        filepath = os.path.join(traces_dir, "timeline.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.export_json(), f, indent=2)

        # Also save individual agent traces
        for trace in self._traces:
            agent_file = os.path.join(traces_dir, f"{trace.agent_name}_{trace.trace_id}.json")
            with open(agent_file, "w", encoding="utf-8") as f:
                json.dump(trace.to_dict(), f, indent=2)

        logger.info("traces_saved", path=traces_dir, count=len(self._traces))
        return traces_dir

    def summary(self) -> dict:
        """Return a concise summary suitable for dashboard display."""
        agents_summary = {}
        for trace in self._traces:
            if trace.agent_name not in agents_summary:
                agents_summary[trace.agent_name] = {
                    "invocations": 0,
                    "total_duration_ms": 0,
                    "last_decision": "",
                    "success_count": 0,
                    "error_count": 0,
                }
            entry = agents_summary[trace.agent_name]
            entry["invocations"] += 1
            entry["total_duration_ms"] += trace.duration_ms
            entry["last_decision"] = trace.decision or ""
            if trace.success:
                entry["success_count"] += 1
            else:
                entry["error_count"] += 1

        return {
            "pipeline_id": self._pipeline_id,
            "total_traces": len(self._traces),
            "active_agents": list(self._active_traces.keys()),
            "agents": agents_summary,
        }


# Singleton instance – import this everywhere
pipeline_tracer = PipelineTracer()
