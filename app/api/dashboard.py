"""Dashboard API – endpoints for real-time pipeline monitoring and trace viewing."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents import list_agents
from app.logging import get_logger
from app.token_tracker import token_tracker
from app.tracing.tracer import pipeline_tracer

router = APIRouter()
logger = get_logger("api.dashboard")

_ws_connections: list[WebSocket] = []


def _get_latest_disk_traces(project_id: str | None = None) -> dict:
    """Read timeline.json from output/<project_id>/traces/ or the latest project."""
    output_dir = "output"
    if not os.path.exists(output_dir):
        return {}

    if project_id:
        filepath = os.path.join(output_dir, project_id, "traces", "timeline.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    # Find the most recently modified timeline.json
    latest_file = None
    latest_mtime = 0
    for root, _, files in os.walk(output_dir):
        if "timeline.json" in files:
            filepath = os.path.join(root, "timeline.json")
            try:
                mtime = os.path.getmtime(filepath)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_file = filepath
            except Exception:
                pass

    if latest_file and os.path.exists(latest_file):
        try:
            with open(latest_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


@router.post("/broadcast")
async def broadcast_event_endpoint(event: dict):
    """Receive live event from CLI process and push to WebSocket UI clients."""
    for ws in list(_ws_connections):
        try:
            await ws.send_json(event)
        except Exception:
            pass
    return {"status": "broadcasted", "listeners": len(_ws_connections)}


@router.get("/projects")
async def list_projects():
    """List all available projects from output/ directory with metadata."""
    output_dir = "output"
    if not os.path.exists(output_dir):
        return []

    projects = []
    for item in os.listdir(output_dir):
        project_dir = os.path.join(output_dir, item)
        if not os.path.isdir(project_dir):
            continue

        timeline_path = os.path.join(project_dir, "traces", "timeline.json")
        if os.path.exists(timeline_path):
            try:
                mtime = os.path.getmtime(timeline_path)
                with open(timeline_path, encoding="utf-8") as f:
                    data = json.load(f)

                from datetime import datetime
                projects.append({
                    "project_id": item,
                    "pipeline_id": data.get("pipeline_id", item),
                    "trace_count": data.get("total_traces", 0),
                    "duration_ms": data.get("total_duration_ms", 0),
                    "last_modified": mtime,
                    "last_modified_iso": datetime.fromtimestamp(mtime, tz=UTC).isoformat(),
                    "active_agents": data.get("active_agents", []),
                })
            except Exception as e:
                logger.warning("failed_to_read_project", project=item, error=str(e))

    # Sort by most recent first
    projects.sort(key=lambda p: p["last_modified"], reverse=True)
    return projects


@router.get("/projects/{project_id}/files")
async def get_project_files(project_id: str):
    """Return the file tree for a project from output/<project_id>/."""
    project_dir = os.path.join("output", project_id)
    if not os.path.isdir(project_dir):
        return {"project_id": project_id, "files": [], "error": "Project not found"}

    def _walk_dir(dirpath: str, rel_prefix: str = "") -> list[dict]:
        entries = []
        try:
            items = sorted(os.listdir(dirpath))
        except OSError:
            return entries

        for item in items:
            full = os.path.join(dirpath, item)
            rel = os.path.join(rel_prefix, item).replace("\\", "/") if rel_prefix else item

            if os.path.isdir(full):
                children = _walk_dir(full, rel)
                entries.append({
                    "name": item,
                    "path": rel,
                    "is_dir": True,
                    "children": children,
                    "size": 0,
                })
            else:
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                ext = os.path.splitext(item)[1].lstrip(".")
                entries.append({
                    "name": item,
                    "path": rel,
                    "is_dir": False,
                    "extension": ext,
                    "size": size,
                })
        return entries

    files = _walk_dir(project_dir)
    return {"project_id": project_id, "files": files}


@router.get("/projects/{project_id}/file-content")
async def get_file_content(project_id: str, path: str):
    """Return the content of a specific file in a project."""
    project_dir = os.path.abspath(os.path.join("output", project_id))
    file_path = os.path.abspath(os.path.join(project_dir, path))

    # Security: ensure the resolved path is within the project directory
    if not file_path.startswith(project_dir):
        return {"error": "Invalid path", "path": path}

    if not os.path.isfile(file_path):
        return {"error": "File not found", "path": path}

    ext = os.path.splitext(path)[1].lstrip(".")
    size = os.path.getsize(file_path)

    # Don't read very large files
    if size > 500_000:
        return {
            "path": path,
            "extension": ext,
            "size": size,
            "content": f"[File too large to display: {size:,} bytes]",
            "truncated": True,
        }

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {"error": str(e), "path": path}

    return {
        "path": path,
        "extension": ext,
        "size": size,
        "content": content,
        "truncated": False,
    }


@router.get("/traces")
async def get_all_traces(project_id: str | None = None):
    """Return all agent traces from disk (persisted) or memory (live pipeline)."""
    # Try disk FIRST - persisted data from previous runs
    disk_traces = _get_latest_disk_traces(project_id)
    if disk_traces.get("traces"):
        logger.info(
            "loading_traces_from_disk",
            project_id=project_id or "latest",
            trace_count=len(disk_traces.get("traces", []))
        )
        return disk_traces

    # Fall back to in-memory for live running pipelines
    mem_traces = pipeline_tracer.export_json()
    if mem_traces.get("traces"):
        logger.info("loading_traces_from_memory", trace_count=len(mem_traces.get("traces", [])))
        return mem_traces

    # Nothing found
    logger.info("no_traces_found")
    return {"pipeline_id": "", "traces": [], "total_traces": 0, "active_agents": []}


@router.get("/traces/{agent_name}")
async def get_agent_traces(agent_name: str, project_id: str | None = None):
    """Return all traces for a specific agent from memory or disk."""
    mem_traces = pipeline_tracer.get_traces_for_agent(agent_name)
    if mem_traces:
        return {
            "agent_name": agent_name,
            "trace_count": len(mem_traces),
            "traces": [t.to_dict() for t in mem_traces],
        }

    disk_traces = _get_latest_disk_traces(project_id)
    all_traces = disk_traces.get("traces", [])
    matching = [t for t in all_traces if t.get("agent_name") == agent_name]

    return {
        "agent_name": agent_name,
        "trace_count": len(matching),
        "traces": matching,
    }


@router.get("/pipeline-state")
async def get_pipeline_state(project_id: str | None = None):
    """Return current pipeline stage, progress, and active agents."""
    trace_data = pipeline_tracer.export_json()
    if not trace_data.get("traces"):
        disk_data = _get_latest_disk_traces(project_id)
        if disk_data:
            trace_data = disk_data

    token_data = token_tracker.summary()
    agents_data = list_agents()

    total_agents = len(agents_data)
    completed_agents = len(set(t.get("agent_name", "") for t in trace_data.get("traces", [])))
    progress_pct = round((completed_agents / max(total_agents, 1)) * 100)

    return {
        "pipeline_id": trace_data.get("pipeline_id", ""),
        "progress_percent": progress_pct,
        "completed_agents": completed_agents,
        "total_agents": total_agents,
        "active_agents": trace_data.get("active_agents", []),
        "total_traces": trace_data.get("total_traces", 0),
        "token_usage": token_data,
        "trace_summary": trace_data,
    }


@router.get("/agents-status")
async def get_agents_status(project_id: str | None = None):
    """Return all agents with their current status and trace summaries."""
    agents = list_agents()
    trace_data = pipeline_tracer.export_json()
    if not trace_data.get("traces"):
        disk_data = _get_latest_disk_traces(project_id)
        if disk_data:
            trace_data = disk_data

    agents_summary = {}
    for trace in trace_data.get("traces", []):
        aname = trace.get("agent_name", "")
        if not aname:
            continue
        if aname not in agents_summary:
            agents_summary[aname] = {
                "invocations": 0,
                "total_duration_ms": 0,
                "last_decision": "",
                "success_count": 0,
                "error_count": 0,
            }
        entry = agents_summary[aname]
        entry["invocations"] += 1
        entry["total_duration_ms"] += trace.get("duration_ms", 0)
        entry["last_decision"] = trace.get("decision", "") or ""
        if trace.get("success", True):
            entry["success_count"] += 1
        else:
            entry["error_count"] += 1

    result = []
    for agent in agents:
        agent_traces = agents_summary.get(agent["name"], {})
        is_active = agent["name"] in trace_data.get("active_agents", [])
        status = "active" if is_active else ("completed" if agent_traces else "idle")

        result.append({
            "name": agent["name"],
            "description": agent["description"],
            "tools": agent["tools"],
            "max_tokens": agent["max_tokens"],
            "status": status,
            "invocations": agent_traces.get("invocations", 0),
            "total_duration_ms": agent_traces.get("total_duration_ms", 0),
            "last_decision": agent_traces.get("last_decision", ""),
            "success_count": agent_traces.get("success_count", 0),
            "error_count": agent_traces.get("error_count", 0),
        })

    return result


@router.get("/token-usage")
async def get_token_usage():
    """Return detailed token usage breakdown."""
    return token_tracker.summary()


@router.websocket("/ws")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time pipeline updates to the dashboard."""
    await websocket.accept()
    _ws_connections.append(websocket)
    logger.info("dashboard_ws_connected", total_connections=len(_ws_connections))

    async def on_event(event: dict):
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    from app.orchestrator.graph import register_event_listener, unregister_event_listener
    register_event_listener(on_event)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data) if data else {}

            if msg.get("type") == "get_state":
                state = await get_pipeline_state()
                await websocket.send_json({"type": "state_update", **state})
            elif msg.get("type") == "get_traces":
                traces = await get_all_traces()
                await websocket.send_json({"type": "traces_update", **traces})
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("dashboard_ws_disconnected")
    finally:
        unregister_event_listener(on_event)
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)
