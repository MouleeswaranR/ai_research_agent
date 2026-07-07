"""Celery tasks wrapping pipeline and agent execution."""

from __future__ import annotations

import asyncio
import json

from app.celery_app import celery_app
from app.logging import get_logger

logger = get_logger("celery_tasks")


@celery_app.task(name="app.orchestrator.tasks.run_pipeline", bind=True, max_retries=0)
def run_pipeline_task(self, project_id: str, idea: str) -> dict:
    """Celery task – runs the full pipeline asynchronously.

    Wraps the async orchestrator in an event loop.
    """
    from app.orchestrator.graph import run_pipeline

    logger.info("celery_pipeline_start", project_id=project_id, task_id=self.request.id)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_pipeline(project_id, idea))
        loop.close()

        logger.info(
            "celery_pipeline_complete",
            project_id=project_id,
            status=result.get("status"),
        )
        return result

    except Exception as e:
        logger.error("celery_pipeline_error", project_id=project_id, error=str(e))
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="app.orchestrator.tasks.run_agent_task", bind=True)
def run_agent_task(self, agent_name: str, project_id: str, context_json: str) -> dict:
    """Celery task – runs a single agent.

    Used for parallel execution or manual re-runs.
    """
    from app.agents import get_agent
    from app.agents.base import PipelineContext

    logger.info("celery_agent_start", agent=agent_name, project_id=project_id)

    try:
        context_data = json.loads(context_json)
        context = PipelineContext(**context_data)

        agent = get_agent(agent_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        output = loop.run_until_complete(agent.run(context))
        loop.close()

        return {
            "agent_name": output.agent_name,
            "artifact_type": output.artifact_type,
            "content": output.content,
            "metadata": output.metadata,
            "success": output.success,
        }

    except Exception as e:
        logger.error("celery_agent_error", agent=agent_name, error=str(e))
        return {"agent_name": agent_name, "success": False, "error": str(e)}
