# Dashboard Connectivity Issue - Analysis & Solutions

## 🔴 Problem Summary

**Issue 1**: Dashboard UI not updating when running `python run_pipeline.py`
**Issue 2**: Cannot view existing traces/artifacts from previous runs
**Issue 3**: No live tracking of pipeline progress in dashboard

## 🔍 Root Cause Analysis

### Issue 1: CLI Runs Independently of FastAPI Server

**Current Architecture**:
```
┌─────────────────┐
│  run_pipeline.py│  ← Standalone script
└─────────────────┘
        │
        ├─> Runs agents directly
        ├─> Saves traces to disk
        └─> NO CONNECTION to FastAPI server

┌─────────────────┐
│  FastAPI Server │  ← Separate process
│  (uvicorn)      │
└─────────────────┘
        │
        ├─> WebSocket endpoint at /api/dashboard/ws
        ├─> REST API for traces
        └─> Dashboard UI at /dashboard

Result: NO COMMUNICATION between CLI and dashboard!
```

**Problem**: `run_pipeline.py` and FastAPI server are **separate processes** with no IPC (Inter-Process Communication).

### Issue 2: Dashboard Only Shows In-Memory Data

**Code Evidence** (`app/api/dashboard.py`):
```python
@router.get("/traces")
async def get_all_traces(project_id: str | None = None):
    mem_traces = pipeline_tracer.export_json()  # ← In-memory only!
    if mem_traces.get("traces"):
        return mem_traces  # Returns empty if no active pipeline
    
    # Only falls back to disk if memory is empty
    disk_traces = _get_latest_disk_traces(project_id)
    return disk_traces
```

**Problem**: Dashboard shows `pipeline_tracer` in-memory data, which is empty when CLI runs separately.

### Issue 3: No Real-Time Event Broadcasting

**Missing Component**: CLI doesn't POST events to FastAPI's `/api/dashboard/broadcast` endpoint.

---

## ✅ Solutions

### Solution 1: Add HTTP Client to CLI for Event Broadcasting

**Modify `run_pipeline.py`** to send events to FastAPI:

```python
import httpx

# Add at top
DASHBOARD_API = os.getenv("DASHBOARD_API_URL", "http://localhost:8000")

async def broadcast_to_dashboard(event: dict):
    """Send event to FastAPI dashboard for WebSocket broadcast."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{DASHBOARD_API}/api/dashboard/broadcast",
                json=event,
                timeout=2.0
            )
    except Exception as e:
        logger.debug("dashboard_broadcast_failed", error=str(e))

# In main():
await broadcast_to_dashboard({"type": "pipeline_started", "project_id": project_id})

# After each agent:
await broadcast_to_dashboard({
    "type": "agent_started",
    "agent": agent.name,
    "stage": "product_strategist"
})

# ... later
await broadcast_to_dashboard({
    "type": "agent_completed",
    "agent": agent.name,
    "stage": "product_strategist",
    "duration_ms": 1234
})
```

### Solution 2: Make Dashboard Load from Disk by Default

**Modify `app/api/dashboard.py`**:

```python
@router.get("/traces")
async def get_all_traces(project_id: str | None = None):
    """Return traces from disk (persisted) or memory (live pipeline)."""
    # ALWAYS check disk first
    disk_traces = _get_latest_disk_traces(project_id)
    if disk_traces.get("traces"):
        return disk_traces
    
    # Fall back to in-memory for live pipelines
    mem_traces = pipeline_tracer.export_json()
    return mem_traces
```

### Solution 3: Add Project List Endpoint

**Add to `app/api/dashboard.py`**:

```python
@router.get("/projects")
async def list_projects():
    """List all projects in output/ directory."""
    output_dir = "output"
    if not os.path.exists(output_dir):
        return []
    
    projects = []
    for item in os.listdir(output_dir):
        project_dir = os.path.join(output_dir, item)
        if os.path.isdir(project_dir):
            timeline_path = os.path.join(project_dir, "traces", "timeline.json")
            if os.path.exists(timeline_path):
                try:
                    mtime = os.path.getmtime(timeline_path)
                    with open(timeline_path, "r") as f:
                        data = json.load(f)
                    
                    projects.append({
                        "project_id": item,
                        "pipeline_id": data.get("pipeline_id", item),
                        "trace_count": data.get("total_traces", 0),
                        "last_modified": datetime.fromtimestamp(mtime).isoformat(),
                        "duration_ms": data.get("total_duration_ms", 0)
                    })
                except Exception:
                    pass
    
    # Sort by most recent first
    projects.sort(key=lambda p: p["last_modified"], reverse=True)
    return projects
```

### Solution 4: Add Project Selector to Dashboard UI

**Add to `app/dashboard/index.html`**:

```html
<!-- Add after header -->
<div class="project-selector">
    <label>Select Project:</label>
    <select id="projectSelect">
        <option value="">-- Live Pipeline --</option>
    </select>
    <button id="refreshProjects">🔄 Refresh</button>
</div>
```

**Add to `app/dashboard/app.js`**:

```javascript
async function loadProjects() {
    try {
        const response = await fetch(`${API_BASE}/api/dashboard/projects`);
        const projects = await response.json();
        
        const select = document.getElementById('projectSelect');
        select.innerHTML = '<option value="">-- Live Pipeline --</option>';
        
        for (const project of projects) {
            const option = document.createElement('option');
            option.value = project.project_id;
            option.textContent = `${project.project_id} (${new Date(project.last_modified).toLocaleString()})`;
            select.appendChild(option);
        }
    } catch (e) {
        console.error('Failed to load projects:', e);
    }
}

// On project change, reload traces
document.getElementById('projectSelect').addEventListener('change', async (e) => {
    const projectId = e.target.value;
    await loadTracesForProject(projectId);
});

async function loadTracesForProject(projectId) {
    const url = projectId 
        ? `${API_BASE}/api/dashboard/traces?project_id=${projectId}`
        : `${API_BASE}/api/dashboard/traces`;
    
    const response = await fetch(url);
    const data = await response.json();
    updateTraces(data);
}

// Load projects on page load
window.addEventListener('DOMContentLoaded', () => {
    loadProjects();
    connectWebSocket();
});
```

### Solution 5: Unified Runner Script

**Create `run_pipeline_live.py`** (starts FastAPI + runs pipeline):

```python
#!/usr/bin/env python
"""Run pipeline with live dashboard updates."""

import asyncio
import sys
import subprocess
import time
import httpx
from multiprocessing import Process

def start_fastapi_server():
    """Start FastAPI server in background."""
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000"
    ])

async def run_pipeline_with_dashboard(idea: str, project_id: str):
    """Run pipeline and send events to dashboard."""
    from run_pipeline import main as pipeline_main
    
    # Wait for server to be ready
    for _ in range(10):
        try:
            async with httpx.AsyncClient() as client:
                await client.get("http://localhost:8000/health")
            break
        except:
            await asyncio.sleep(1)
    
    # Run pipeline
    await pipeline_main(idea, project_id, max_retries=2, provider=None)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--idea", required=True)
    parser.add_argument("--project-id", default="live-app")
    args = parser.parse_args()
    
    # Start FastAPI in background
    server_proc = Process(target=start_fastapi_server, daemon=True)
    server_proc.start()
    
    print("⏳ Starting FastAPI server...")
    time.sleep(3)
    
    print(f"🚀 Dashboard available at: http://localhost:8000/dashboard")
    print(f"🔄 Running pipeline for: {args.project_id}")
    
    # Run pipeline with dashboard updates
    asyncio.run(run_pipeline_with_dashboard(args.idea, args.project_id))
    
    print("\n✅ Pipeline complete! Dashboard remains running.")
    print("   Press Ctrl+C to stop server.")
    
    server_proc.join()
```

---

## 🛠️ Quick Fixes to Apply NOW

### Fix 1: Make Dashboard Load from Disk (IMMEDIATE)

**File**: `app/api/dashboard.py`

```python
# Change line ~55:
@router.get("/traces")
async def get_all_traces(project_id: str | None = None):
    # Try disk FIRST (persisted data)
    disk_traces = _get_latest_disk_traces(project_id)
    if disk_traces.get("traces"):
        logger.info("loading_traces_from_disk", project_id=project_id or "latest")
        return disk_traces
    
    # Fall back to in-memory (live pipeline)
    mem_traces = pipeline_tracer.export_json()
    if mem_traces.get("traces"):
        logger.info("loading_traces_from_memory")
        return mem_traces
    
    return {"pipeline_id": "", "traces": [], "total_traces": 0}
```

### Fix 2: Add Projects List Endpoint

**File**: `app/api/dashboard.py` (add this route):

```python
@router.get("/projects")
async def list_projects():
    """List all available projects from output/ directory."""
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
                with open(timeline_path, "r") as f:
                    data = json.load(f)
                
                projects.append({
                    "project_id": item,
                    "trace_count": data.get("total_traces", 0),
                    "duration_ms": data.get("total_duration_ms", 0),
                    "last_modified": mtime,
                    "last_modified_iso": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                })
            except Exception as e:
                logger.warning("failed_to_read_project", project=item, error=str(e))
    
    projects.sort(key=lambda p: p["last_modified"], reverse=True)
    return projects
```

### Fix 3: Auto-Load Latest Project on Dashboard Open

**File**: `app/dashboard/app.js` (modify init):

```javascript
// Add after DOMContentLoaded:
async function init() {
    connectWebSocket();
    
    // Try to load latest project from disk
    try {
        const response = await fetch(`${API_BASE}/api/dashboard/traces`);
        const data = await response.json();
        
        if (data.traces && data.traces.length > 0) {
            console.log(`Loaded ${data.traces.length} traces from disk`);
            updateTraces(data);
            updatePipelineState(data);
        } else {
            console.log('No traces found. Waiting for live pipeline...');
        }
    } catch (e) {
        console.error('Failed to load initial traces:', e);
    }
}

window.addEventListener('DOMContentLoaded', init);
```

---

## 📊 Expected Behavior After Fixes

### Before (Broken):
```
1. User runs: python run_pipeline.py --idea "..." --project-id test
2. Pipeline completes, saves traces to output/test/traces/
3. User opens: http://localhost:8000/dashboard
4. Dashboard shows: "No traces. Waiting for pipeline..."
5. Result: NO VISIBILITY ❌
```

### After (Fixed):
```
1. User runs: python run_pipeline.py --idea "..." --project-id test
2. Pipeline completes, saves traces to output/test/traces/
3. User opens: http://localhost:8000/dashboard
4. Dashboard auto-loads output/test/traces/timeline.json
5. Shows: 14 agents, traces, token usage, progress
6. Result: FULL VISIBILITY ✅
```

---

## 🧪 Testing Steps

### Test 1: View Existing Project
```bash
# 1. Run pipeline (if not already done)
python run_pipeline.py --idea "calculator" --project-id test-calc

# 2. Start FastAPI server
uvicorn app.main:app --reload --port 8000

# 3. Open dashboard
# http://localhost:8000/dashboard

# Expected: Should show test-calc traces, agents, progress
```

### Test 2: Live Tracking (Future Enhancement)
```bash
# Will work after adding HTTP broadcast to run_pipeline.py
python run_pipeline_live.py --idea "todo app" --project-id live-test

# Dashboard updates in real-time as agents run
```

---

## 🎯 Priority Fixes

**IMMEDIATE (15 min)**:
1. ✅ Change `/traces` to load from disk first
2. ✅ Add `/projects` endpoint
3. ✅ Auto-load latest project on dashboard init

**SHORT-TERM (1 hour)**:
4. Add project selector dropdown in UI
5. Add refresh button for project list
6. Add HTTP broadcast calls in `run_pipeline.py`

**LONG-TERM (future)**:
7. Unified `run_pipeline_live.py` script
8. Real-time progress bar updates
9. Agent-level live status indicators

---

## 📝 Summary

**Root Cause**: CLI (`run_pipeline.py`) runs independently of FastAPI server with no IPC.

**Quick Fix**: Make dashboard load persisted traces from disk by default instead of only checking in-memory data.

**Result**: Users can view past pipeline runs immediately after opening dashboard.

**For Live Updates**: Need to add HTTP client to CLI to POST events to FastAPI's broadcast endpoint.

**Status**: ⚠️ Partially working - can view persisted data, but no live updates yet.
