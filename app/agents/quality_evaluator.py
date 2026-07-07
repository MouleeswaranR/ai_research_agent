"""Quality Evaluator Agent – scores overall project quality."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.tools.complexity import CyclomaticComplexityTool, MaintainabilityIndexTool
from app.tools.security_scanner import BanditScanTool
from app.tools.test_runner import PytestRunnerTool


class QualityEvaluatorAgent(BaseAgent):
    name = "quality_evaluator"
    description = "Evaluates overall project quality across multiple dimensions"
    max_tokens = 512

    def __init__(self) -> None:
        super().__init__()
        self.tools = [
            PytestRunnerTool(),
            CyclomaticComplexityTool(),
            MaintainabilityIndexTool(),
            BanditScanTool(),
        ]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("evaluating_quality", project_id=context.project_id)
        self._build_tool_context(context)

        system_prompt = (
            "You are a quality evaluator. Score the project across dimensions.\n"
            "Output JSON with keys: overall_score (0-100), "
            "dimensions: {code_quality, test_coverage, security, architecture, "
            "documentation, maintainability} (each 0-100), "
            "strengths[], improvements[], production_ready (bool), summary (1 sentence)"
        )

        code_summary = "\n".join(
            f"- {fname} ({len(content)} chars)" for fname, content in context.code_files.items()
        )
        user_prompt = (
            f"Project: {context.idea[:200]}\n\n"
            f"Files:\n{code_summary}\n\n"
            f"Test files: {list(context.test_files.keys())}\n\n"
            f"Architecture:\n{context.architecture[:500]}\n\n"
            "Score the project quality."
        )

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        self.logger.info(
            "quality_scored",
            project_id=context.project_id,
            overall=result.get("overall_score", 0) if isinstance(result, dict) else 0,
        )

        return AgentOutput(
            agent_name=self.name,
            artifact_type="quality_evaluation",
            content=content,
            metadata=result if isinstance(result, dict) else {},
        )
