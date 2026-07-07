"""Pipeline API – start pipeline, get status, WebSocket updates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logging import get_logger
from app.models.pipeline_run import PipelineRun
from app.models.project import Project
from app.models.review_result import ReviewResult
from app.orchestrator.tasks import run_pipeline_task
from app.schemas import PipelineStatusResponse, ReviewResultResponse
from app.token_tracker import token_tracker

router = APIRouter()
logger = get_logger("api.pipeline")


@router.post("/{project_id}/pipeline/start", response_model=PipelineStatusResponse, status_code=202)
async def start_pipeline(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Kick off the development pipeline for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create pipeline run record
    pipeline_run = PipelineRun(project_id=project.id, status="running", current_stage="prd")
    db.add(pipeline_run)
    await db.flush()
    await db.refresh(pipeline_run)

    # Update project status
    project.status = "running"
    await db.flush()

    # Dispatch Celery task
    run_pipeline_task.delay(str(project.id), project.idea)

    logger.info("pipeline_started", project_id=str(project.id), run_id=str(pipeline_run.id))
    return pipeline_run


@router.get("/{project_id}/pipeline/status", response_model=list[PipelineStatusResponse])
async def get_pipeline_status(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get pipeline run status for a project."""
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
    )
    runs = result.scalars().all()
    if not runs:
        raise HTTPException(status_code=404, detail="No pipeline runs found")
    return runs


@router.get("/{project_id}/pipeline/reviews", response_model=list[ReviewResultResponse])
async def get_review_results(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get all review gate results for a project's latest pipeline run."""
    # Get latest run
    run_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="No pipeline runs found")

    result = await db.execute(
        select(ReviewResult)
        .where(ReviewResult.pipeline_run_id == run.id)
        .order_by(ReviewResult.created_at.asc())
    )
    return result.scalars().all()


@router.get("/{project_id}/pipeline/tokens")
async def get_token_usage(project_id: uuid.UUID):
    """Get token usage summary for the current session."""
    return token_tracker.summary()


@router.websocket("/{project_id}/pipeline/ws")
async def pipeline_websocket(websocket: WebSocket, project_id: uuid.UUID):
    """WebSocket endpoint for real-time pipeline stage updates."""
    await websocket.accept()
    logger.info("ws_connected", project_id=str(project_id))

    try:
        while True:
            # Client sends "ping" or "status" messages
            data = await websocket.receive_text()

            # Respond with current token tracking info
            summary = token_tracker.summary()
            await websocket.send_json({
                "type": "status",
                "project_id": str(project_id),
                "token_usage": summary,
            })
    except WebSocketDisconnect:
        logger.info("ws_disconnected", project_id=str(project_id))
