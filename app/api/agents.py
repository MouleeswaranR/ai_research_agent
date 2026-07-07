"""Agents API – agent health, metrics, registry."""

from __future__ import annotations

from fastapi import APIRouter

from app.agents import list_agents
from app.schemas import AgentHealthResponse

router = APIRouter()


@router.get("/", response_model=list[AgentHealthResponse])
async def get_all_agents():
    """List all registered agents with their tools and status."""
    agents = list_agents()
    return [
        AgentHealthResponse(
            name=a["name"],
            status="active",
            tools=a["tools"],
        )
        for a in agents
    ]


@router.get("/{agent_name}")
async def get_agent_detail(agent_name: str):
    """Get details for a specific agent."""
    agents = list_agents()
    for a in agents:
        if a["name"] == agent_name:
            return {
                "name": a["name"],
                "description": a["description"],
                "tools": a["tools"],
                "max_tokens": a["max_tokens"],
                "status": "active",
            }
    return {"error": f"Agent '{agent_name}' not found"}
