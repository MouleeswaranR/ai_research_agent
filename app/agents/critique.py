"""Critique Agent – provides deep, targeted critique on coding agent outputs.

Runs BETWEEN every coding-related agent (Code Generator, Test Writer, Refactor)
to identify specific issues, suggest improvements, and generate actionable
feedback that feeds into the self-learning loop.
"""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext


class CritiqueAgent(BaseAgent):
    name = "critique"
    description = "Provides deep critique on code output, identifies improvements, feeds self-learning loop"
    max_tokens = 512

    def __init__(self) -> None:
        super().__init__()
        self.tools = []

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info(
            "critiquing",
            project_id=context.project_id,
            stage=context.current_stage,
            attempt=context.retry_count,
        )

        def _safe(v, n=99999):
            if v is None: return ""
            if isinstance(v, dict): return json.dumps(v, indent=2)[:n]
            return str(v)[:n]

        code_dump = "\n".join(
            f"### {fname}\n```\n{_safe(content, 1500)}\n```"
            for fname, content in context.code_files.items()
        )

        system_prompt = (
            "You are an elite code critic. Your job is to find EVERY issue in the code.\n"
            "You are NOT a pass/fail gate. You provide CONSTRUCTIVE critique.\n"
            "Be specific and actionable. Reference exact files and lines.\n\n"
            "Analyze for:\n"
            "1. BUGS: Logic errors, off-by-one, null refs, unhandled edge cases\n"
            "2. ARCHITECTURE: Coupling, cohesion, separation of concerns\n"
            "3. PERFORMANCE: Unnecessary loops, memory leaks, O(n^2) patterns\n"
            "4. SECURITY: XSS, injection, hardcoded secrets, unsafe patterns\n"
            "5. UX: Missing states, accessibility, responsive issues\n"
            "6. COMPLETENESS: Missing features, incomplete implementations\n\n"
            "Output JSON:\n"
            "- critique_items[] (each: {category, severity: critical|high|medium|low, "
            "file, description, suggestion, priority: 1-5})\n"
            "- overall_quality: 0-100\n"
            "- top_3_improvements[] (actionable strings)\n"
            "- ready_for_review: bool"
        )

        user_prompt = (
            f"Stage: {context.current_stage}\n"
            f"Project idea: {context.idea[:200]}\n\n"
            f"Code to critique:\n{code_dump}\n\n"
            "Provide deep, specific critique."
        )

        # On escalation attempts (retry_count > 0), route to the critique_escalation model (Nemotron 550B)
        original_name = self.name
        if context.retry_count > 0:
            self.name = "critique_escalation"

        try:
            result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        finally:
            self.name = original_name

        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        ready = result.get("ready_for_review", False) if isinstance(result, dict) else False
        quality = result.get("overall_quality", 0) if isinstance(result, dict) else 0
        items = result.get("critique_items", []) if isinstance(result, dict) else []
        improvements = result.get("top_3_improvements", []) if isinstance(result, dict) else []

        self.logger.info(
            "critique_complete",
            project_id=context.project_id,
            quality_score=quality,
            issues_found=len(items),
            ready_for_review=ready,
        )

        return AgentOutput(
            agent_name=self.name,
            artifact_type="critique",
            content=content,
            metadata={
                "overall_quality": quality,
                "issue_count": len(items),
                "ready_for_review": ready,
                "top_improvements": improvements,
            },
        )
