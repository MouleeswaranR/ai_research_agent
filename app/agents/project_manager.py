"""Project Manager Agent – breaks PRD or ElevatedSpec into FeatureSet."""

import json

from pydantic import ValidationError

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.schemas.architecture import FeatureSet


class ProjectManagerAgent(BaseAgent):
    name = "project_manager"
    description = "Breaks spec into feature set and sprint plan"
    max_tokens = 4096
    output_schema = FeatureSet

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("creating_task_backlog", project_id=context.project_id)

        if settings.ENABLE_GRAPH_PIPELINE:
            return await self._run_graph(context)

        system_prompt = (
            "You are a senior project manager. Break down a PRD into an actionable task backlog as JSON.\n"
            "Be concise. Each task must be implementable in ≤4 hours.\n"
            "JSON keys: epics[] (each: {name, description, tasks[]}), sprint_plan[]"
        )

        user_prompt = f"PRD:\n{context.prd}"
        critique = self._format_critique(context)
        if critique:
            user_prompt += critique

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        return AgentOutput(
            agent_name=self.name,
            artifact_type="task_backlog",
            content=content,
        )

    async def _run_graph(self, context: PipelineContext) -> AgentOutput:
        system_prompt = (
            "You are a senior project manager.\n"
            "Break down the ElevatedSpec into a structured FeatureSet.\n"
            "respond with JSON matching this schema only:\n"
            "{\n"
            '  "features": [\n'
            '    {\n'
            '      "id": "feat_1",\n'
            '      "name": "...",\n'
            '      "description": "...",\n'
            '      "user_story": "...",\n'
            '      "acceptance_criteria": ["..."],\n'
            '      "priority": "must_have",\n'
            '      "layer": "backend",\n'
            '      "depends_on": []\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_prompt = f"ElevatedSpec:\n{context.prd}"
        error_context = ""

        for attempt in range(3):
            prompt = user_prompt + (f"\n\nPrevious error: {error_context}" if error_context else "")
            result = await self.call_llm(system_prompt, prompt, json_mode=True)
            content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

            try:
                fs = FeatureSet.model_validate_json(content)
                fs.validate_dependency_ids()
                return AgentOutput(agent_name=self.name, artifact_type="feature_set", content=content)
            except (ValidationError, ValueError) as err:
                error_context = str(err)
                self.logger.warning("feature_set_validation_retry", attempt=attempt+1, error=error_context)

        return AgentOutput(agent_name=self.name, artifact_type="feature_set", content=content)
