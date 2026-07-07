"""Agents package – registry of all available agents."""

from app.agents.code_generator import CodeGeneratorAgent
from app.agents.code_reviewer import CodeReviewerAgent
from app.agents.critique import CritiqueAgent
from app.agents.deployment import DeploymentAgent
from app.agents.monitoring import MonitoringAgent
from app.agents.planner import PlannerAgent
from app.agents.product_strategist import ProductStrategistAgent
from app.agents.project_manager import ProjectManagerAgent
from app.agents.quality_evaluator import QualityEvaluatorAgent
from app.agents.refactor import RefactorAgent
from app.agents.security_architect import SecurityArchitectAgent
from app.agents.self_evaluator import SelfEvaluationAgent
from app.agents.system_architect import SystemArchitectAgent
from app.agents.test_writer import TestWriterAgent

# Agent registry – ordered by pipeline stage
AGENT_REGISTRY = {
    "product_strategist": ProductStrategistAgent,
    "project_manager": ProjectManagerAgent,
    "system_architect": SystemArchitectAgent,
    "security_architect": SecurityArchitectAgent,
    "planner": PlannerAgent,
    "code_generator": CodeGeneratorAgent,
    "test_writer": TestWriterAgent,
    "code_reviewer": CodeReviewerAgent,
    "refactor": RefactorAgent,
    "deployment": DeploymentAgent,
    "monitoring": MonitoringAgent,
    "quality_evaluator": QualityEvaluatorAgent,
    "critique": CritiqueAgent,
    "self_evaluator": SelfEvaluationAgent,
}


def get_agent(name: str):
    """Instantiate an agent by name."""
    cls = AGENT_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown agent: {name}")
    return cls()


def list_agents() -> list[dict]:
    """Return metadata for all registered agents."""
    result = []
    for name, cls in AGENT_REGISTRY.items():
        instance = cls()
        result.append({
            "name": name,
            "description": instance.description,
            "tools": [t.name for t in instance.tools],
            "max_tokens": instance.max_tokens,
        })
    return result
