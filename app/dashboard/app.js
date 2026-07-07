/**
 * Auto Dev Company – Dashboard Application
 *
 * Features:
 * - Live pipeline monitoring via WebSocket + REST polling
 * - Project explorer: browse files, view code, artifacts, traces
 * - Real-time stage-by-stage updates during pipeline execution
 */

// ── Constants ────────────────────────────────────────────────
const API_BASE = window.location.origin;
const WS_URL = `ws://${window.location.host}/api/dashboard/ws`;
const POLL_INTERVAL_MS = 5000;
const MAX_LOG_ENTRIES = 100;

// Agent color palette for consistent visual identity
const AGENT_COLORS = {
    product_strategist: '#6366f1',
    project_manager: '#8b5cf6',
    system_architect: '#3b82f6',
    security_architect: '#06b6d4',
    planner: '#14b8a6',
    code_generator: '#10b981',
    test_writer: '#22c55e',
    code_reviewer: '#eab308',
    refactor: '#f59e0b',
    critique: '#f97316',
    self_evaluator: '#ef4444',
    deployment: '#ec4899',
    monitoring: '#d946ef',
    quality_evaluator: '#a855f7',
};

// File extension → icon mapping
const FILE_ICONS = {
    js: '📜', ts: '📘', py: '🐍', html: '🌐', css: '🎨', json: '📋',
    md: '📝', yml: '⚙️', yaml: '⚙️', toml: '⚙️', txt: '📄', sh: '🔧',
    dockerfile: '🐳', sql: '🗃️', env: '🔐', gitignore: '🚫',
};

// ── State ────────────────────────────────────────────────────
let ws = null;
let isConnected = false;
let agentsData = [];
let tracesData = [];
let tokenData = {};
let pipelineState = {};
let pollTimer = null;

// Project explorer state
let projectsList = [];
let selectedProjectId = null;
let selectedFilePath = null;

// ── DOM References ───────────────────────────────────────────
const statusDot = document.getElementById('statusDot');
const connectionText = document.getElementById('connectionText');
const providerBadge = document.getElementById('providerBadge');
const statAgents = document.getElementById('statAgents');
const statAgentsDetail = document.getElementById('statAgentsDetail');
const statCalls = document.getElementById('statCalls');
const statCallsDetail = document.getElementById('statCallsDetail');
const statProgress = document.getElementById('statProgress');
const statProgressDetail = document.getElementById('statProgressDetail');
const statCost = document.getElementById('statCost');
const statCostDetail = document.getElementById('statCostDetail');
const progressBarFill = document.getElementById('progressBarFill');
const agentsGrid = document.getElementById('agentsGrid');
const traceList = document.getElementById('traceList');
const tokenBars = document.getElementById('tokenBars');
const logStream = document.getElementById('logStream');

// ══════════════════════════════════════════════════════════════
// TAB NAVIGATION
// ══════════════════════════════════════════════════════════════

function switchTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });

    if (tabName === 'projects') {
        fetchProjects();
    }
}

function switchDetailTab(tabName) {
    document.querySelectorAll('.detail-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.dtab === tabName);
    });
    document.querySelectorAll('.detail-tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `dtab-${tabName}`);
    });
}

// ══════════════════════════════════════════════════════════════
// WEBSOCKET CONNECTION
// ══════════════════════════════════════════════════════════════

function connectWebSocket() {
    try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            isConnected = true;
            updateConnectionStatus(true);
            addLog('system', 'WebSocket connected', 'success');
            ws.send(JSON.stringify({ type: 'get_state' }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWSMessage(data);
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        ws.onclose = () => {
            isConnected = false;
            updateConnectionStatus(false);
            addLog('system', 'WebSocket disconnected. Reconnecting...', 'warning');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
            isConnected = false;
            updateConnectionStatus(false);
        };
    } catch (e) {
        console.error('WebSocket error:', e);
        setTimeout(connectWebSocket, 5000);
    }
}

function handleWSMessage(data) {
    switch (data.type) {
        case 'state_update':
            updatePipelineState(data);
            break;
        case 'traces_update':
            updateTraces(data);
            break;
        case 'agent_started':
            handleAgentStarted(data);
            break;
        case 'agent_completed':
            handleAgentCompleted(data);
            break;
        case 'loop_attempt':
            addLog(data.stage, `Self-learning loop attempt ${data.attempt}/${data.max_retries}`, 'warning');
            break;
        case 'critique_result':
            addLog('critique', `Quality: ${data.quality}/100 | Issues: ${data.issues} | Ready: ${data.ready}`, data.ready ? 'success' : 'warning');
            break;
        case 'self_eval_decision':
            const cls = data.decision === 'accept' ? 'success' : (data.decision === 'escalate' ? 'error' : 'warning');
            addLog('self_evaluator', `Decision: ${data.decision.toUpperCase()} (improvement: ${data.improvement_score}/100)`, cls);
            break;
        case 'pipeline_started':
            addLog('system', `Pipeline started: ${data.project_id}`, 'success');
            break;
        case 'pipeline_completed':
            addLog('system', 'Pipeline completed!', 'success');
            if (data.token_summary) updateTokenDisplay(data.token_summary);
            break;
        case 'pong':
            break;
        default:
            console.log('Unknown WS message:', data);
    }
}

function updateConnectionStatus(connected) {
    if (connected) {
        statusDot.classList.remove('disconnected');
        connectionText.textContent = 'Connected';
    } else {
        statusDot.classList.add('disconnected');
        connectionText.textContent = 'Disconnected';
    }
}

// ══════════════════════════════════════════════════════════════
// REST API
// ══════════════════════════════════════════════════════════════

async function fetchJSON(url) {
    try {
        const res = await fetch(`${API_BASE}${url}`);
        if (!res.ok) return null;
        return await res.json();
    } catch (e) {
        return null;
    }
}

async function pollState() {
    const agents = await fetchJSON('/api/dashboard/agents-status');
    if (agents) {
        agentsData = agents;
        renderAgents(agents);
    }

    const state = await fetchJSON('/api/dashboard/pipeline-state');
    if (state) {
        updatePipelineState(state);
    }

    const traces = await fetchJSON('/api/dashboard/traces');
    if (traces) {
        updateTraces(traces);
    }

    const tokens = await fetchJSON('/api/dashboard/token-usage');
    if (tokens) {
        updateTokenDisplay(tokens);
    }

    const health = await fetchJSON('/health');
    if (health) {
        const providerName = (health.llm_provider || 'unknown').toUpperCase().replace('_', ' ');
        providerBadge.textContent = providerName;
    }
}

// ══════════════════════════════════════════════════════════════
// DASHBOARD RENDER FUNCTIONS
// ══════════════════════════════════════════════════════════════

function renderAgents(agents) {
    if (!agents || agents.length === 0) return;

    const activeCount = agents.filter(a => a.status === 'active').length;
    const completedCount = agents.filter(a => a.status === 'completed').length;

    statAgents.textContent = agents.length;
    statAgentsDetail.textContent = activeCount > 0 ? `${activeCount} active` : `${completedCount} completed`;

    agentsGrid.innerHTML = agents.map(agent => {
        const color = AGENT_COLORS[agent.name] || '#6366f1';
        const statusClass = agent.status || 'idle';
        const invocations = agent.invocations || 0;
        const duration = agent.total_duration_ms ? `${(agent.total_duration_ms / 1000).toFixed(1)}s` : '—';

        return `
            <div class="agent-card ${statusClass}" data-agent="${agent.name}" onclick="showAgentTrace('${agent.name}')" style="--agent-color: ${color}">
                <div class="agent-header">
                    <span class="agent-name">${formatAgentName(agent.name)}</span>
                    <span class="agent-status-dot"></span>
                </div>
                <div class="agent-desc">${agent.description || ''}</div>
                <div class="agent-stats">
                    <span class="agent-stat">⚡ ${invocations}</span>
                    <span class="agent-stat">⏱ ${duration}</span>
                </div>
            </div>
        `;
    }).join('');
}

function updatePipelineState(state) {
    pipelineState = state;
    const progress = state.progress_percent || 0;

    statProgress.textContent = `${progress}%`;
    progressBarFill.style.width = `${progress}%`;

    const activeAgents = state.active_agents || [];
    statProgressDetail.textContent = activeAgents.length > 0
        ? `Running: ${activeAgents.map(formatAgentName).join(', ')}`
        : (progress >= 100 ? 'Completed' : 'Idle');

    const completedAgents = new Set();
    if (state.trace_summary && state.trace_summary.agents) {
        Object.keys(state.trace_summary.agents).forEach(name => completedAgents.add(name));
    }

    document.querySelectorAll('.pipeline-stage').forEach(el => {
        const stage = el.dataset.stage;
        el.classList.remove('completed', 'active', 'error');

        if (activeAgents.includes(stage)) {
            el.classList.add('active');
        } else if (completedAgents.has(stage)) {
            el.classList.add('completed');
        }
    });

    if (state.token_usage) {
        updateTokenDisplay(state.token_usage);
    }
}

function updateTraces(data) {
    const traces = data.traces || [];
    if (traces.length === 0) return;

    tracesData = traces;
    traceList.innerHTML = renderTraceItems(traces);
}

function renderTraceItems(traces) {
    return traces.map((trace, idx) => {
        const color = AGENT_COLORS[trace.agent_name] || '#6366f1';
        const duration = trace.duration_ms ? `${(trace.duration_ms / 1000).toFixed(2)}s` : '...';
        const steps = trace.thinking_steps || [];
        const successIcon = trace.success ? '✅' : '❌';

        return `
            <div class="trace-item" id="trace-${idx}">
                <div class="trace-header" onclick="toggleTrace(${idx})">
                    <div class="trace-agent-info">
                        <span style="color: ${color}">${successIcon}</span>
                        <span class="trace-agent-name" style="color: ${color}">${formatAgentName(trace.agent_name)}</span>
                        <span class="trace-stage-badge">${trace.stage || '—'}</span>
                    </div>
                    <div class="trace-meta">
                        <span class="trace-duration">${duration}</span>
                        <span>${trace.model_used || ''}</span>
                        <span class="trace-chevron">▼</span>
                    </div>
                </div>
                <div class="trace-body">
                    ${trace.system_prompt ? `
                        <div class="trace-section">
                            <div class="trace-section-title">System Prompt</div>
                            <div class="trace-content">${escapeHtml(trace.system_prompt)}</div>
                        </div>
                    ` : ''}
                    ${trace.user_prompt ? `
                        <div class="trace-section">
                            <div class="trace-section-title">User Prompt</div>
                            <div class="trace-content">${escapeHtml(trace.user_prompt.substring(0, 1500))}</div>
                        </div>
                    ` : ''}
                    ${trace.llm_raw_response ? `
                        <div class="trace-section">
                            <div class="trace-section-title">LLM Response</div>
                            <div class="trace-content">${escapeHtml(trace.llm_raw_response)}</div>
                        </div>
                    ` : ''}
                    ${steps.length > 0 ? `
                        <div class="trace-section">
                            <div class="trace-section-title">Thinking Steps (${steps.length})</div>
                            <div class="trace-thinking-steps">
                                ${steps.map(s => `
                                    <div class="thinking-step">
                                        <span class="thinking-step-type">${s.step_type}</span>
                                        <span class="thinking-step-content">${escapeHtml(s.content)}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    ${trace.token_usage && Object.keys(trace.token_usage).length > 0 ? `
                        <div class="trace-section">
                            <div class="trace-section-title">Token Usage</div>
                            <div class="trace-content">${JSON.stringify(trace.token_usage, null, 2)}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function updateTokenDisplay(tokens) {
    if (!tokens) return;

    statCalls.textContent = tokens.total_calls || 0;
    const totalTokens = (tokens.total_input_tokens || 0) + (tokens.total_output_tokens || 0);
    statCallsDetail.textContent = `${totalTokens.toLocaleString()} tokens`;

    statCost.textContent = `$${(tokens.total_cost_usd || 0).toFixed(4)}`;
    statCostDetail.textContent = `${tokens.total_input_tokens?.toLocaleString() || 0} in / ${tokens.total_output_tokens?.toLocaleString() || 0} out`;

    tokenData = tokens;

    const perAgent = tokens.per_agent || {};
    const agentNames = Object.keys(perAgent);

    if (agentNames.length === 0) return;

    const maxTokens = Math.max(...agentNames.map(n => (perAgent[n].input_tokens || 0) + (perAgent[n].output_tokens || 0)), 1);

    tokenBars.innerHTML = agentNames.map(name => {
        const data = perAgent[name];
        const total = (data.input_tokens || 0) + (data.output_tokens || 0);
        const pct = Math.round((total / maxTokens) * 100);
        const color = AGENT_COLORS[name] || '#6366f1';

        return `
            <div class="token-bar-row">
                <span class="token-bar-label">${formatAgentName(name)}</span>
                <div class="token-bar-track">
                    <div class="token-bar-fill" style="width: ${pct}%; background: ${color}">${data.calls || 0} calls</div>
                </div>
                <span class="token-bar-value">${total.toLocaleString()}</span>
            </div>
        `;
    }).join('');
}

// ── Event Handlers ───────────────────────────────────────────

function handleAgentStarted(data) {
    addLog(data.agent, 'Started execution', 'success');
    const card = document.querySelector(`.agent-card[data-agent="${data.agent}"]`);
    if (card) {
        card.classList.remove('idle', 'completed');
        card.classList.add('active');
    }
    const stage = document.querySelector(`.pipeline-stage[data-stage="${data.agent}"]`);
    if (stage) {
        stage.classList.add('active');
    }
    pollState();
}

function handleAgentCompleted(data) {
    addLog(data.agent, `Completed (${data.content_length || 0} chars)`, 'success');
    const card = document.querySelector(`.agent-card[data-agent="${data.agent}"]`);
    if (card) {
        card.classList.remove('active');
        card.classList.add('completed');
    }
    const stage = document.querySelector(`.pipeline-stage[data-stage="${data.agent}"]`);
    if (stage) {
        stage.classList.remove('active');
        stage.classList.add('completed');
    }
    pollState();
}

// ══════════════════════════════════════════════════════════════
// PROJECT EXPLORER
// ══════════════════════════════════════════════════════════════

async function fetchProjects() {
    const data = await fetchJSON('/api/dashboard/projects');
    if (data) {
        projectsList = data;
        renderProjectList(data);
    }
}

function renderProjectList(projects) {
    const container = document.getElementById('projectList');
    if (!projects || projects.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📂</div>
                <div class="empty-state-text">No projects yet.<br>Run a pipeline to generate one.</div>
            </div>
        `;
        return;
    }

    container.innerHTML = projects.map(p => {
        const isSelected = p.project_id === selectedProjectId;
        const date = new Date(p.last_modified * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        return `
            <div class="project-card ${isSelected ? 'selected' : ''}" onclick="selectProject('${p.project_id}')">
                <div class="project-card-name">📦 ${p.project_id}</div>
                <div class="project-card-meta">
                    <span>🧠 ${p.trace_count || 0} traces</span>
                    <span>📅 ${date}</span>
                </div>
            </div>
        `;
    }).join('');
}

async function selectProject(projectId) {
    selectedProjectId = projectId;
    selectedFilePath = null;

    // Update sidebar selection
    renderProjectList(projectsList);

    // Show detail header
    const header = document.getElementById('projectDetailHeader');
    const tabs = document.getElementById('detailTabs');
    const emptyState = document.querySelector('.project-detail-empty');

    header.style.display = 'block';
    tabs.style.display = 'flex';
    if (emptyState) emptyState.style.display = 'none';

    document.getElementById('projectDetailTitle').textContent = `📦 ${projectId}`;

    // Fetch all data in parallel
    const [filesData, tracesData] = await Promise.all([
        fetchJSON(`/api/dashboard/projects/${projectId}/files`),
        fetchJSON(`/api/dashboard/traces?project_id=${projectId}`),
    ]);

    // Render file tree
    if (filesData && filesData.files) {
        renderFileTree(filesData.files);
    }

    // Render artifacts (filter from files)
    if (filesData && filesData.files) {
        const artifactsDir = filesData.files.find(f => f.name === 'artifacts' && f.is_dir);
        if (artifactsDir && artifactsDir.children) {
            renderArtifacts(projectId, artifactsDir.children);
        } else {
            document.getElementById('artifactsGrid').innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🧩</div>
                    <div class="empty-state-text">No artifacts found for this project.</div>
                </div>
            `;
        }
    }

    // Render traces
    const traceContainer = document.getElementById('projectTraceList');
    if (tracesData && tracesData.traces && tracesData.traces.length > 0) {
        traceContainer.innerHTML = renderTraceItems(tracesData.traces);
    } else {
        traceContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🧠</div>
                <div class="empty-state-text">No traces found for this project.</div>
            </div>
        `;
    }

    // Show project meta
    const project = projectsList.find(p => p.project_id === projectId);
    if (project) {
        const dur = project.duration_ms ? `${(project.duration_ms / 1000).toFixed(1)}s` : '—';
        document.getElementById('projectDetailMeta').innerHTML = `
            <span>🧠 ${project.trace_count || 0} traces</span>
            <span>⏱ ${dur}</span>
        `;
    }

    // Default to files tab
    switchDetailTab('files');
}

// ── File Tree ────────────────────────────────────────────────

function renderFileTree(files) {
    const container = document.getElementById('fileTree');
    container.innerHTML = buildFileTreeHTML(files, 0);
}

function buildFileTreeHTML(items, depth) {
    return items.map(item => {
        const indent = depth * 16;
        if (item.is_dir) {
            const icon = '📁';
            return `
                <div class="file-tree-item dir" style="padding-left: ${indent}px" onclick="toggleDir(this, event)">
                    <span class="file-tree-arrow">▶</span>
                    <span class="file-tree-icon">${icon}</span>
                    <span class="file-tree-name">${item.name}</span>
                </div>
                <div class="file-tree-children" style="display:none;">
                    ${item.children ? buildFileTreeHTML(item.children, depth + 1) : ''}
                </div>
            `;
        } else {
            const ext = item.extension || '';
            const icon = FILE_ICONS[ext.toLowerCase()] || '📄';
            const size = formatBytes(item.size);
            return `
                <div class="file-tree-item file" style="padding-left: ${indent + 16}px" onclick="viewFile('${item.path}')" data-path="${item.path}" title="${item.path} (${size})">
                    <span class="file-tree-icon">${icon}</span>
                    <span class="file-tree-name">${item.name}</span>
                    <span class="file-tree-size">${size}</span>
                </div>
            `;
        }
    }).join('');
}

function toggleDir(el, event) {
    event.stopPropagation();
    const children = el.nextElementSibling;
    if (children && children.classList.contains('file-tree-children')) {
        const isOpen = children.style.display !== 'none';
        children.style.display = isOpen ? 'none' : 'block';
        const arrow = el.querySelector('.file-tree-arrow');
        if (arrow) arrow.textContent = isOpen ? '▶' : '▼';
        el.classList.toggle('open', !isOpen);
    }
}

async function viewFile(path) {
    if (!selectedProjectId) return;
    selectedFilePath = path;

    // Highlight active file in tree
    document.querySelectorAll('.file-tree-item.file').forEach(el => {
        el.classList.toggle('active', el.dataset.path === path);
    });

    // Update header
    document.getElementById('codeViewerPath').textContent = path;

    const data = await fetchJSON(`/api/dashboard/projects/${selectedProjectId}/file-content?path=${encodeURIComponent(path)}`);
    if (data && data.content !== undefined) {
        document.getElementById('codeViewerSize').textContent = formatBytes(data.size);
        const codeEl = document.getElementById('codeContent');
        codeEl.textContent = data.content;
    } else if (data && data.error) {
        document.getElementById('codeContent').textContent = `Error: ${data.error}`;
    }
}

// ── Artifacts ────────────────────────────────────────────────

async function renderArtifacts(projectId, artifactFiles) {
    const container = document.getElementById('artifactsGrid');
    if (!artifactFiles || artifactFiles.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🧩</div>
                <div class="empty-state-text">No artifacts found.</div>
            </div>
        `;
        return;
    }

    // Sort by name
    const sorted = [...artifactFiles].sort((a, b) => a.name.localeCompare(b.name));

    container.innerHTML = sorted.map(file => {
        const name = file.name.replace('.json', '');
        const displayName = formatAgentName(name);
        const color = Object.entries(AGENT_COLORS).find(([k]) => name.includes(k));
        const barColor = color ? color[1] : '#6366f1';

        return `
            <div class="artifact-card" onclick="viewArtifact('${projectId}', '${file.path}')" style="--artifact-color: ${barColor}">
                <div class="artifact-icon">🧩</div>
                <div class="artifact-name">${displayName}</div>
                <div class="artifact-size">${formatBytes(file.size)}</div>
            </div>
        `;
    }).join('');
}

async function viewArtifact(projectId, path) {
    // Switch to files tab and show the artifact content
    switchDetailTab('files');
    await viewFile(path);
}

// ══════════════════════════════════════════════════════════════
// UI INTERACTIONS
// ══════════════════════════════════════════════════════════════

function toggleTrace(idx) {
    const el = document.getElementById(`trace-${idx}`);
    if (el) {
        el.classList.toggle('expanded');
    }
}

async function showAgentTrace(agentName) {
    const data = await fetchJSON(`/api/dashboard/traces/${agentName}`);
    if (data && data.traces && data.traces.length > 0) {
        updateTraces(data);
        setTimeout(() => {
            const first = document.getElementById('trace-0');
            if (first) first.classList.add('expanded');
        }, 100);
    }
}

// ══════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ══════════════════════════════════════════════════════════════

function formatAgentName(name) {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), 2);
    return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`;
}

function addLog(agent, message, level = '') {
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    const color = AGENT_COLORS[agent] || '#94a3b8';

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-agent" style="color: ${color}">${formatAgentName(agent)}</span>
        <span class="log-msg ${level}">${message}</span>
    `;

    logStream.appendChild(entry);

    while (logStream.children.length > MAX_LOG_ENTRIES) {
        logStream.removeChild(logStream.firstChild);
    }

    logStream.scrollTop = logStream.scrollHeight;
}

// ══════════════════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════════════════

async function init() {
    addLog('system', 'Dashboard initializing...', '');

    // Try to load latest project traces from disk
    try {
        const tracesResponse = await fetchJSON('/api/dashboard/traces');
        if (tracesResponse && tracesResponse.traces && tracesResponse.traces.length > 0) {
            console.log(`✅ Loaded ${tracesResponse.traces.length} traces from ${tracesResponse.pipeline_id}`);
            updateTraces(tracesResponse);
            updateStatsFromTraces(tracesResponse);
            addLog('system', `Loaded ${tracesResponse.traces.length} traces from ${tracesResponse.pipeline_id}`, 'success');
        } else {
            addLog('system', 'No previous pipeline runs. Waiting for new pipeline...', '');
        }
    } catch (e) {
        console.error('Failed to load initial traces:', e);
    }

    // Initial data fetch
    await pollState();

    // Connect WebSocket for real-time updates
    connectWebSocket();

    // Periodic polling as fallback
    pollTimer = setInterval(pollState, POLL_INTERVAL_MS);

    // WebSocket keepalive
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000);

    addLog('system', 'Dashboard ready', 'success');
}

function updateStatsFromTraces(data) {
    const traces = data.traces || [];
    const agents = new Set(traces.map(t => t.agent_name).filter(Boolean));
    const totalTokens = traces.reduce((sum, t) => sum + (t.token_usage?.total_tokens || 0), 0);

    if (statAgents) statAgents.textContent = agents.size;
    if (statAgentsDetail) statAgentsDetail.textContent = `${agents.size} executed`;
    if (statCalls) statCalls.textContent = traces.length;
    if (statCallsDetail) statCallsDetail.textContent = `${totalTokens.toLocaleString()} tokens`;
    if (statProgress) statProgress.textContent = '100%';
    if (statProgressDetail) statProgressDetail.textContent = data.pipeline_id || 'Completed';
    if (progressBarFill) progressBarFill.style.width = '100%';

    const firstTrace = traces[0];
    if (firstTrace && firstTrace.provider && providerBadge) {
        providerBadge.textContent = firstTrace.provider.toUpperCase();
    }
}

// Start
document.addEventListener('DOMContentLoaded', init);
