"""Planner Agent – converts features into technical specs or ProjectGraph."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.schemas.graph import ProjectGraph
from app.tools.ast_analyzer import ASTAnalyzerTool
from app.tools.search import FindFilesTool, GrepSearchTool


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Converts features into technical specs with interfaces or ProjectGraph"
    max_tokens = 4096
    output_schema = ProjectGraph

    def __init__(self) -> None:
        super().__init__()
        self.tools = [GrepSearchTool(), FindFilesTool(), ASTAnalyzerTool()]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("creating_tech_spec", project_id=context.project_id)
        self._build_tool_context(context)

        if settings.ENABLE_GRAPH_PIPELINE:
            system_prompt = (
                "You are a senior technical planner.\n"
                "Construct a ProjectGraph mapping all files and folders from ArchitectureOutput and FeatureSet.\n"
                "For every file node, populate planned_imports, planned_exports, purpose, and depends_on.\n"
                "Folder nodes must have type='folder' and empty imports/exports/depends_on.\n"
                "respond with JSON matching this schema only:\n"
                "{\n"
                '  "project_id": "' + context.project_id + '",\n'
                '  "nodes": {\n'
                '    "app/main.py": {\n'
                '      "id": "app/main.py", "path": "app/main.py", "type": "file",\n'
                '      "language": "python", "purpose": "Main entry point",\n'
                '      "related_feature_ids": [], "planned_imports": [], "planned_exports": [],\n'
                '      "depends_on": [], "status": "pending"\n'
                '    }\n'
                "  }\n"
                "}"
            )
            user_prompt = (
                f"FeatureSet:\n{context.prd[:1500]}\n\n"
                f"ArchitectureOutput:\n{context.architecture[:2000]}\n\n"
                "Construct the full ProjectGraph."
            )
        else:
            system_prompt = (
                "You are a senior technical planner. Create a technical specification as JSON.\n"
                "JSON keys: feature_name, modules[], data_flow[], edge_cases[], acceptance_criteria[], implementation_order[]"
            )
            user_prompt = (
                f"Architecture:\n{context.architecture[:2000]}\n\n"
                f"Security:\n{context.security_spec[:1000]}\n\n"
                "Create technical spec for implementation."
            )

        critique = self._format_critique(context)
        if critique:
            user_prompt += critique

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        self.logger.info("tech_spec_created", project_id=context.project_id)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="tech_spec",
            content=content,
        )
