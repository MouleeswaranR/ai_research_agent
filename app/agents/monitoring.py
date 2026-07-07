"""Monitoring Agent – generates monitoring and observability configs."""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.tools.file_ops import WriteFileTool


class MonitoringAgent(BaseAgent):
    name = "monitoring"
    description = "Generates monitoring dashboards, alerting rules, and health check configs"
    max_tokens = 1536

    def __init__(self) -> None:
        super().__init__()
        self.tools = [WriteFileTool()]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("generating_monitoring", project_id=context.project_id)
        self._build_tool_context(context)

        system_prompt = (
            "You are a monitoring engineer. Generate observability config as JSON.\n"
            "Be concise.\n"
            "JSON keys: health_checks[] (each: {name, endpoint, interval, alert_threshold}), "
            "metrics[] (each: {name, type, labels[], description}), "
            "dashboards[] (each: {name, panels[] (each: {title, query, type})}), "
            "alerting_rules[] (each: {name, condition, severity, notification_channel}), "
            "logging: {format, level, structured, correlation_id}"
        )

        user_prompt = (
            f"Architecture:\n{context.architecture[:1000]}\n\n"
            f"Files: {list(context.code_files.keys())}\n\n"
            "Generate monitoring configs."
        )

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        self.logger.info("monitoring_generated", project_id=context.project_id)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="monitoring",
            content=content,
        )
