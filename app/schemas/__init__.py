"""Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── Project ───────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    idea: str = Field(..., min_length=10, description="Describe the software to build")


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    idea: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Artifact ──────────────────────────────────────────────────

class ArtifactResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    agent_name: str
    artifact_type: str
    content: str
    metadata_json: dict | None = None
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Pipeline ──────────────────────────────────────────────────

class PipelineStartRequest(BaseModel):
    """Empty body – just triggers the pipeline for a project."""
    pass


class PipelineStatusResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    current_stage: str
    status: str
    retry_count: int
    token_usage: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Review ────────────────────────────────────────────────────

class ReviewResultResponse(BaseModel):
    id: uuid.UUID
    pipeline_run_id: uuid.UUID
    gate_name: str
    stage: str
    passed: bool
    issues: list | None = None
    scores: dict | None = None
    critique: str | None = None
    attempt: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Agent Health ──────────────────────────────────────────────

class AgentHealthResponse(BaseModel):
    name: str
    status: str  # active | inactive
    tools: list[str]
    total_invocations: int = 0
    pass_rate: float | None = None


# ── Token Usage ───────────────────────────────────────────────

class TokenUsageSummary(BaseModel):
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    per_agent: dict
