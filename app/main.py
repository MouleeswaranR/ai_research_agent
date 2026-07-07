"""FastAPI application entry point – serves API and dashboard."""

from __future__ import annotations

import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Fix Windows MIME type registry issues for CSS and JS
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from app.logging import get_logger, setup_logging

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the application."""
    setup_logging()
    logger.info("app_starting", host=settings.host, port=settings.port)
    yield
    logger.info("app_shutting_down")


from app.config import settings

app = FastAPI(
    title="Auto Dev Company",
    description="Autonomous multi-agent software development pipeline",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS for local dashboard development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount API routers ────────────────────────────────────────

from app.api.agents import router as agents_router
from app.api.dashboard import router as dashboard_router
from app.api.pipeline import router as pipeline_router
from app.api.projects import router as projects_router

app.include_router(projects_router, prefix="/api/projects", tags=["Projects"])
app.include_router(agents_router, prefix="/api/agents", tags=["Agents"])
app.include_router(pipeline_router, prefix="/api/projects", tags=["Pipeline"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])

# ── Serve dashboard static files ─────────────────────────────

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")

if os.path.isdir(DASHBOARD_DIR):
    @app.get("/dashboard/static/styles.css", include_in_schema=False)
    async def serve_styles():
        """Force explicit MIME type for styles to fix Windows registry issues."""
        return FileResponse(os.path.join(DASHBOARD_DIR, "styles.css"), media_type="text/css")

    @app.get("/dashboard/static/app.js", include_in_schema=False)
    async def serve_js():
        """Force explicit MIME type for javascript."""
        return FileResponse(os.path.join(DASHBOARD_DIR, "app.js"), media_type="application/javascript")

    app.mount("/dashboard/static", StaticFiles(directory=DASHBOARD_DIR), name="dashboard_static")


@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serve the main dashboard HTML page."""
    index_path = os.path.join(DASHBOARD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"error": "Dashboard not found", "path": DASHBOARD_DIR}


# ── Health check ─────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Return system health status."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "llm_provider": settings.llm_provider,
        "model": settings.active_model,
        "trace_enabled": settings.trace_enabled,
    }


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")
