"""Code Reviewer Agent – MANDATORY GATE. Full static analysis suite."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.tools.ast_analyzer import ASTAnalyzerTool
from app.tools.complexity import CyclomaticComplexityTool, MaintainabilityIndexTool
from app.tools.dependency_scanner import DependencyScannerTool
from app.tools.linter import RuffLintTool
from app.tools.security_scanner import BanditScanTool
from app.tools.test_runner import PytestRunnerTool


class CodeReviewerAgent(BaseAgent):
    name = "code_reviewer"
    description = "MANDATORY GATE – runs full static analysis, security scan, and quality checks"
    max_tokens = 512  # Minimal output – just verdict

    def __init__(self) -> None:
        super().__init__()
        self.tools = [
            RuffLintTool(),
            BanditScanTool(),
            CyclomaticComplexityTool(),
            MaintainabilityIndexTool(),
            ASTAnalyzerTool(),
            PytestRunnerTool(),
            DependencyScannerTool(),
        ]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("review_gate", project_id=context.project_id, stage=context.current_stage)
        self._build_tool_context(context)

        # Step 1: Run all analysis tools
        results = {}

        lint_tool = self.tools[0]
        results["lint"] = lint_tool._run(".")

        security_tool = self.tools[1]
        results["security"] = security_tool._run(".")

        complexity_tool = self.tools[2]
        results["complexity"] = complexity_tool._run(".")

        mi_tool = self.tools[3]
        results["maintainability"] = mi_tool._run(".")

        # Step 2: Run tests if test files exist
        if context.test_files:
            test_tool = self.tools[5]
            results["tests"] = test_tool._run("tests/", with_coverage=True)

        # Step 3: Ask LLM to produce a structured verdict
        system_prompt = (
            "You are a strict code reviewer. Analyze tool outputs and produce a JSON verdict.\n"
            "Be extremely concise.\n"
            "JSON keys: pass (bool), issues[] (each: {severity, file, line, message, category}), "
            "scores: {security (0-100), quality (0-100), coverage (0-100), complexity (0-100), "
            "maintainability (0-100)}, summary (1 sentence), blocking_issues_count (int)"
        )

        analysis_summary = "\n".join(
            f"### {tool}\n{output[:500]}" for tool, output in results.items()
        )

        user_prompt = (
            f"Stage: {context.current_stage}\n\n"
            f"Analysis Results:\n{analysis_summary}\n\n"
            f"Thresholds: coverage>={settings.coverage_threshold}%, "
            f"complexity<={settings.complexity_threshold}, "
            f"security_block={settings.security_severity_block}\n\n"
            "Produce review verdict."
        )

        verdict = await self.call_llm(system_prompt, user_prompt, json_mode=True)

        content = json.dumps(verdict, indent=2) if isinstance(verdict, dict) else str(verdict)
        passed = verdict.get("pass", False) if isinstance(verdict, dict) else False

        self.logger.info(
            "review_verdict",
            project_id=context.project_id,
            stage=context.current_stage,
            passed=passed,
            blocking_issues=verdict.get("blocking_issues_count", 0) if isinstance(verdict, dict) else -1,
        )

        return AgentOutput(
            agent_name=self.name,
            artifact_type="review",
            content=content,
            metadata={
                "passed": passed,
                "scores": verdict.get("scores", {}) if isinstance(verdict, dict) else {},
                "stage": context.current_stage,
            },
            success=passed,
        )
