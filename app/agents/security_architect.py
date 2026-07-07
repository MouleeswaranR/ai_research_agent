"""Security Architect Agent – auth, permissions, threat modeling or SecurityReviewResult."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.schemas.architecture import SecurityReviewResult
from app.tools.dependency_scanner import DependencyScannerTool
from app.tools.security_scanner import BanditScanTool


class SecurityArchitectAgent(BaseAgent):
    name = "security_architect"
    description = "Defines auth, permissions, and performs threat modeling"
    max_tokens = 4096
    output_schema = SecurityReviewResult

    def __init__(self) -> None:
        super().__init__()
        self.tools = [BanditScanTool(), DependencyScannerTool()]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("security_analysis", project_id=context.project_id)
        self._build_tool_context(context)

        if settings.ENABLE_GRAPH_PIPELINE:
            system_prompt = (
                "You are a security architect.\n"
                "Review the ArchitectureOutput for OWASP Top 10 vulnerabilities.\n"
                "respond with JSON matching this schema only:\n"
                "{\n"
                '  "approved": true,\n'
                '  "findings": ["..."],\n'
                '  "blocking": false\n'
                "}"
            )
            user_prompt = f"ArchitectureOutput:\n{context.architecture}\n\nReview architecture."
        else:
            system_prompt = (
                "You are a security architect. Define security specification as JSON.\n"
                "Cover OWASP Top 10. Be concise.\n"
                "JSON keys: auth_strategy, permission_model, threat_model[], security_requirements[], "
                "encryption, input_validation_rules[], rate_limiting, cors_policy"
            )
            user_prompt = f"Architecture:\n{context.architecture}\n\nDefine security spec."

        critique = self._format_critique(context)
        if critique:
            user_prompt += critique

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        is_blocking = result.get("blocking", False) if isinstance(result, dict) else False

        self.logger.info("security_spec_created", project_id=context.project_id, blocking=is_blocking)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="security_spec",
            content=content,
            success=not is_blocking,
            metadata={"blocking": is_blocking, "findings": result.get("findings", []) if isinstance(result, dict) else []},
        )
