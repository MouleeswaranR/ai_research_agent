"""Deployment Agent – generates deployment artifacts."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.tools.docker_tools import DockerfileGeneratorTool, DockerfileValidatorTool
from app.tools.file_ops import WriteFileTool


class DeploymentAgent(BaseAgent):
    name = "deployment"
    description = "Generates Dockerfile, docker-compose, CI/CD pipeline configs"
    max_tokens = 2048

    def __init__(self) -> None:
        super().__init__()
        self.tools = [DockerfileGeneratorTool(), DockerfileValidatorTool(), WriteFileTool()]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("generating_deployment", project_id=context.project_id)
        self._build_tool_context(context)

        system_prompt = (
            "You are a DevOps engineer. Generate deployment configuration as JSON.\n"
            "Be concise.\n"
            "JSON keys: dockerfile (string), docker_compose (string), "
            "ci_pipeline: {provider, stages[], config (string)}, "
            "env_vars[] (each: {name, description, required}), "
            "health_check: {endpoint, interval, timeout}"
        )

        file_list = list(context.code_files.keys())
        user_prompt = (
            f"Architecture:\n{context.architecture[:1500]}\n\n"
            f"Files: {file_list}\n\n"
            "Generate deployment configs."
        )

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        self.logger.info("deployment_generated", project_id=context.project_id)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="deployment",
            content=content,
        )
