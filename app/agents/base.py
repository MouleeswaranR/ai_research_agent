"""Base agent abstract class – all agents inherit from this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool as LangChainTool

from app.agents.llm_client import call_llm, call_llm_json
from app.logging import get_logger


@dataclass
class AgentOutput:
    """Standard output from any agent."""

    agent_name: str
    artifact_type: str
    content: str
    metadata: dict = field(default_factory=dict)
    success: bool = True
    error: str | None = None


@dataclass
class PipelineContext:
    """Shared context passed through the pipeline."""

    project_id: str
    idea: str
    # Artifacts produced by previous agents
    prd: str = ""
    architecture: str = ""
    security_spec: str = ""
    tech_spec: str = ""
    code_files: dict[str, str] = field(default_factory=dict)
    test_files: dict[str, str] = field(default_factory=dict)
    review_critiques: list[str] = field(default_factory=list)
    # Current stage metadata
    current_stage: str = ""
    retry_count: int = 0


class BaseAgent(ABC):
    """Abstract base for all pipeline agents."""

    name: str = "base_agent"
    description: str = ""
    max_tokens: int = 1024
    tools: list[LangChainTool] = []

    def __init__(self) -> None:
        self.logger = get_logger(f"agent.{self.name}")

    @abstractmethod
    async def run(self, context: PipelineContext) -> AgentOutput:
        """Execute the agent's task and return output."""
        ...

    async def run_with_trace(self, context: PipelineContext) -> AgentOutput:
        """Execute the agent with automatic tracing of the thinking chain."""
        from app.config import settings
        from app.tracing.tracer import pipeline_tracer

        if not settings.trace_enabled:
            return await self.run(context)

        trace = pipeline_tracer.start_trace(
            agent_name=self.name,
            stage=context.current_stage,
            attempt=context.retry_count + 1,
        )
        trace.add_step("agent_started", f"Agent '{self.name}' starting execution")

        try:
            output = await self.run(context)
            trace.decision = output.metadata.get("decision", "completed")

            # Try to parse output content for the trace
            try:
                trace.parsed_output = (
                    __import__("json").loads(output.content)
                    if output.content.startswith("{")
                    else {"raw": output.content[:500]}
                )
            except Exception:
                trace.parsed_output = {"raw": output.content[:500]}

            trace.add_step(
                "agent_completed",
                f"Agent '{self.name}' completed successfully",
                artifact_type=output.artifact_type,
            )
            pipeline_tracer.end_trace(self.name, success=True)
            return output

        except Exception as exc:
            trace.add_step("agent_error", f"Agent '{self.name}' failed: {exc}")
            pipeline_tracer.end_trace(self.name, success=False, error=str(exc))
            raise

    async def call_llm(
        self, system_prompt: str, user_prompt: str, *, json_mode: bool = False
    ) -> str | dict:
        """Call the active LLM provider with token budget enforcement."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if json_mode:
            result = await call_llm_json(
                messages, agent_name=self.name, max_tokens=self.max_tokens
            )
            return result
        else:
            result = await call_llm(
                messages, agent_name=self.name, max_tokens=self.max_tokens
            )
            return result["content"]

    def _build_tool_context(self, context: PipelineContext) -> None:
        """Set project_id on all sandboxed tools."""
        for tool in self.tools:
            if hasattr(tool, "project_id"):
                tool.project_id = context.project_id

    def _format_critique(self, context: PipelineContext) -> str:
        """Format previous review critiques for injection into prompts."""
        if not context.review_critiques:
            return ""
        return (
            "\n\n## PREVIOUS REVIEW FEEDBACK (MUST ADDRESS)\n"
            + "\n---\n".join(context.review_critiques[-3:])
        )
