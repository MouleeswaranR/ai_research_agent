"""Product Strategist Agent – generates PRD or ElevatedSpec from an idea."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.schemas.architecture import ElevatedSpec


class ProductStrategistAgent(BaseAgent):
    name = "product_strategist"
    description = "Defines product vision, MVP scope, and generates PRD"
    max_tokens = 4096
    output_schema = ElevatedSpec

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("generating_prd", project_id=context.project_id)

        if settings.ENABLE_GRAPH_PIPELINE:
            system_prompt = (
                "You are a senior product strategist.\n"
                "Elevate the user idea into a detailed specification.\n"
                "respond with JSON matching this schema only:\n"
                "{\n"
                '  "original_idea": "...",\n'
                '  "project_title": "...",\n'
                '  "elevated_description": "...",\n'
                '  "problem_statement": "...",\n'
                '  "target_users": ["..."],\n'
                '  "tech_stack": {"frontend": "...", "backend": "...", "database": "...", "devops": "...", "rationale": "..."},\n'
                '  "non_functional_requirements": ["..."]\n'
                "}"
            )
        else:
            system_prompt = (
                "You are a senior product strategist. Output a Product Requirements Document (PRD) as JSON.\n"
                "Be concise. Focus on actionable requirements.\n"
                "JSON keys: product_name, vision, target_users, mvp_features, non_functional_requirements[], tech_constraints[], success_metrics[]"
            )

        user_prompt = f"Create a PRD for this idea:\n{context.idea}"
        critique = self._format_critique(context)
        if critique:
            user_prompt += critique

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        self.logger.info("prd_generated", project_id=context.project_id)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="prd",
            content=content,
            metadata={"features_count": len(result.get("mvp_features", [])) if isinstance(result, dict) else 0},
        )
