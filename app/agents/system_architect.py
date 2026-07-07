"""System Architect Agent – designs architecture, API contracts, DB schema, or ArchitectureOutput."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.schemas.architecture import ArchitectureOutput
from app.tools.schema_validator import JSONSchemaValidatorTool


class SystemArchitectAgent(BaseAgent):
    name = "system_architect"
    description = "Designs system architecture, API contracts, and DB schema"
    max_tokens = 4096
    output_schema = ArchitectureOutput

    def __init__(self) -> None:
        super().__init__()
        self.tools = [JSONSchemaValidatorTool()]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("designing_architecture", project_id=context.project_id)

        if settings.ENABLE_GRAPH_PIPELINE:
            system_prompt = (
                "You are a senior system architect.\n"
                "Design the DependencyManifest and ProjectFileTree into ArchitectureOutput.\n"
                "respond with JSON matching this schema only:\n"
                "{\n"
                '  "dependencies": {\n'
                '    "frontend": [], "backend": [], "devops": [], "shared": []\n'
                "  },\n"
                '  "file_tree": {\n'
                '    "project_id": "' + context.project_id + '",\n'
                '    "root": {\n'
                '      "name": "root", "path": ".", "type": "folder", "purpose": "Project root",\n'
                '      "related_feature_ids": [], "children": []\n'
                "    }\n"
                "  }\n"
                "}"
            )
            user_prompt = f"FeatureSet:\n{context.prd}\n\nDesign the file tree and dependencies."
        else:
            system_prompt = (
                "You are a senior system architect. Design the architecture as JSON.\n"
                "Be concise. Use production-ready patterns.\n"
                "CRITICAL: Always design a modular, multi-file architecture (e.g., separate HTML, CSS, and JS files for web apps). NEVER design single-file monolithic applications.\n"
                "JSON keys: architecture_style, components[], api_contracts[], db_schema, infrastructure"
            )
            user_prompt = f"PRD:\n{context.prd}\n\nDesign the architecture."

        critique = self._format_critique(context)
        if critique:
            user_prompt += critique

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        self.logger.info("architecture_designed", project_id=context.project_id)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="architecture",
            content=content,
        )
