# 🤖 Auto Dev Company — Autonomous Multi-Agent Software Builder

> **Autonomous software development pipeline powered by NVIDIA NIM & multi-agent orchestration.**  
> Transform natural language software ideas into complete, production-ready codebases with graph-based topological code execution, per-agent LLM routing, closed-loop self-evaluation, and real-time reasoning visualization.

---

## 🌟 Key Features

- **🚀 NVIDIA NIM & Groq Model Integration**: Powered by NVIDIA NIM (`meta/llama-3.3-70b-instruct`) as the primary high-performance LLM endpoint, with seamless failover to Groq (`llama-3.3-70b-versatile`).
- **🎯 Per-Agent Model Routing (`AGENT_MODEL_MAP`)**: Routes specialized NVIDIA NIM models (Nemotron 120B, GLM 5.2, DeepSeek v4 Flash/Pro, Kimi k2.6) dynamically to specific pipeline agents based on task complexity.
- **🗺️ Graph-Based Pipeline Execution**: Optional `ENABLE_GRAPH_PIPELINE` mode composing Phase 1 outputs into validated Pydantic schemas (`ElevatedSpec` → `FeatureSet` → `ArchitectureOutput` → `SecurityReviewResult` → `ProjectGraph`) and generating code in topological dependency order.
- **👥 14 Specialized AI Agents**: Dedicated agents for product strategy, architecture, security, code generation, test writing, critique, self-evaluation, deployment, and monitoring.
- **🔄 Closed-Loop Self-Learning**: Iterative `Code Generator ↔ Critique ↔ Self-Evaluation` loop. The pipeline automatically critiques generated code, checks for bugs and security vulnerabilities, and retries generation until quality thresholds are met.
- **🔬 Agent Thinking Trace System**: Complete visibility into agent reasoning chains, prompt contexts, decisions, latencies, and token costs recorded as structured trace artifacts.
- **📊 Real-Time Web Dashboard**: Premium dark-themed, glassmorphic UI served via FastAPI & WebSockets for monitoring pipeline progress, viewing active agent thinking traces, inspecting token breakdown, and tracking live event logs.
- **🛡️ Isolated Docker Sandbox**: Safe, containerized execution environment for linting, security analysis (Bandit, Radon, Safety), and running unit test suites.

---

## 🏗️ Architecture & Pipeline Flow

The development process is structured into 5 distinct phases executed across 14 specialized agents:

```mermaid
flowchart TD
    Idea([💡 User Idea]) --> Phase1

    subgraph Phase1["Phase 1: Planning & Structured Architecture"]
        PS[Product Strategist\nElevatedSpec] --> PM[Project Manager\nFeatureSet]
        PM --> SA[System Architect\nArchitectureOutput]
        SA --> SEC[Security Architect\nSecurityReviewResult]
        SEC --> PL[Planner Agent\nProjectGraph]
    end

    Phase1 --> Choice{ENABLE_GRAPH_PIPELINE}

    Choice -- "true" --> GraphExec["🕸️ Graph Executor\n(Topological Level Ordering)"]
    Choice -- "false" --> Phase2

    subgraph Phase2["Phase 2: Code Generation & Self-Learning Loop"]
        CG[Code Generator] --> CR[Critique Agent]
        CR --> SE[Self-Evaluation Agent]
        SE -- "improve" --> CG
    end

    GraphExec --> Phase3
    SE -- "accept" --> Phase3

    subgraph Phase3["Phase 3: Test Generation Loop"]
        TW[Test Writer] --> CR2[Critique Agent]
        CR2 --> SE2[Self-Evaluation Agent]
        SE2 -- "improve" --> TW
    end

    SE2 -- "accept" --> Phase4

    subgraph Phase4["Phase 4: Code Refactoring Loop"]
        RF[Refactor Agent] --> CR3[Critique Agent]
        CR3 --> SE3[Self-Evaluation Agent]
        SE3 -- "improve" --> RF
    end

    SE3 -- "accept" --> Phase5

    subgraph Phase5["Phase 5: Deployment & Quality Assurance"]
        DP[Deployment Agent]
        MN[Monitoring Agent]
        QE[Quality Evaluator]
    end

    Phase5 --> Done([🎉 Complete Production Code & Artifacts])
```

---

## 🎯 Model Routing (`AGENT_MODEL_MAP`)

When running with `LLM_PROVIDER=nvidia_nim`, the pipeline dynamically routes requests to optimal NVIDIA NIM models per agent:

| Agent Name | Default NIM Model | Purpose |
| :--- | :--- | :--- |
| **Product Strategist** | `meta/llama-3.3-70b-instruct` | Product vision & spec elevation |
| **Project Manager** | `nvidia/nemotron-3-super-120b-a12b` | Feature breakdown & dependency validation |
| **System Architect** | `nvidia/nemotron-3-super-120b-a12b` | System design & file tree structure |
| **Security Architect** | `nvidia/nemotron-3-super-120b-a12b` | Threat modeling & security review |
| **Planner** | `z-ai/glm-5.2` | Technical spec & ProjectGraph construction |
| **Code Generator** | `z-ai/glm-5.2` | Code generation |
| **Code Escalation** | `deepseek-ai/deepseek-v4-pro` | High-complexity code generation |
| **Critique Agent** | `deepseek-ai/deepseek-v4-flash` | Deep code critique & bug hunting |
| **Self Evaluator** | `meta/llama-3.3-70b-instruct` | Iteration evaluation & decision gate |
| **Test Writer** | `deepseek-ai/deepseek-v4-flash` | Unit & integration test generation |
| **Refactor Agent** | `moonshotai/kimi-k2.6` | DRY/SOLID refactoring |
| **Deployment / Monitoring** | `meta/llama-3.3-70b-instruct` | DevOps & monitoring configs |
| **Quality Evaluator** | `nvidia/nemotron-3-super-120b-a12b` | Project scoring & assessment |

*Note: On Groq failover (`LLM_PROVIDER=groq`), model routing is bypassed and `GROQ_MODEL` is used for all agents.*

---

## 🛠️ Required Software & Infrastructure

Before running the pipeline, ensure the following tools are installed and available:

| Software / Service | Purpose | Recommended Version / Note |
| :--- | :--- | :--- |
| **Python** | Primary Runtime | `3.10+` or `3.12+` |
| **Docker Desktop** | Sandbox execution & containers | Must be running for sandbox execution |
| **Redis** | Task broker & pub/sub | `6.0+` (via Docker or local service) |
| **PostgreSQL / Neon DB** | Persistent state & project data | Neon DB cloud connection or local Postgres |
| **NVIDIA NIM API Key** | Primary LLM Provider | [Get NIM API Key](https://build.nvidia.com/) |
| **Groq API Key** *(Optional)* | Fallback LLM Provider | [Get Groq Key](https://console.groq.com/) |

### Quick Start Redis Container
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### ⚡ One-Shot All-in-One Setup (Recommended)

Run all setups (Redis, Postgres, Celery worker, FastAPI server, & Web Dashboard) in a single command:

```bash
# Docker Compose (All services containerized)
docker compose up -d --build

# Or use the single-click launcher script:
# Windows PowerShell:
.\scripts\run_all.ps1

# Linux / macOS Bash:
chmod +x ./scripts/run_all.sh && ./scripts/run_all.sh

# Windows Command Prompt:
.\scripts\run_all.bat
```

---

### 1. Manual Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/your-org/ai-software-builder-agent.git
cd ai-software-builder-agent

# Install dependencies in editable mode
pip install -e ".[dev]"
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and fill in your API credentials:

```bash
cp .env.example .env
```

Edit your `.env` file:

```ini
# Primary LLM Provider: "nvidia_nim" or "groq"
LLM_PROVIDER=nvidia_nim

# Enable Graph-Based Topological Execution
ENABLE_GRAPH_PIPELINE=false

# NVIDIA NIM Configuration
NVIDIA_NIM_API_KEY=nvapi-your-key-here
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_NIM_MODEL=meta/llama-3.3-70b-instruct

# Groq Configuration (Fallback)
GROQ_API_KEY=gsk_your-key-here
GROQ_MODEL=llama-3.3-70b-versatile

# Infrastructure
DATABASE_URL=postgresql://user:pass@host/neondb?sslmode=require
REDIS_URL=redis://localhost:6379/0
```

---

### 3. Launching the Web Server & Dashboard

Start the FastAPI application:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open your browser and navigate to:
👉 **`http://localhost:8000/dashboard`**

---

### 4. Running the Standalone CLI Pipeline

You can run the full multi-agent pipeline directly from the command line:

```bash
# Run with default idea (Calculator Web App) using NVIDIA NIM
python run_pipeline.py

# Run with a custom idea and project ID
python run_pipeline.py --idea "Build a responsive Kanban board in HTML/CSS/JS with local storage persistence" --project-id kanban-app --max-retries 3

# Force fallback to Groq LLM
python run_pipeline.py --provider groq
```

---

## 📁 Project Directory Structure

```
ai-software-builder-agent/
├── app/
│   ├── agents/             # 14 specialized agent definitions & base classes
│   │   ├── base.py         # Abstract BaseAgent & PipelineContext
│   │   ├── llm_client.py   # Unified NVIDIA NIM / Groq client & per-agent router
│   │   ├── critique.py     # Code Critique Agent
│   │   ├── self_evaluator.py # Self-Evaluation Agent
│   │   └── ...            # Strategist, Architect, Generator, Refactor, etc.
│   ├── api/                # FastAPI endpoint routers
│   │   ├── dashboard.py    # Dashboard REST & WebSocket endpoints
│   │   ├── pipeline.py     # Pipeline management API
│   │   ├── projects.py     # Project CRUD API
│   │   └── agents.py       # Agent status & health API
│   ├── dashboard/          # Dashboard frontend assets
│   │   ├── index.html      # Glassmorphic UI layout
│   │   ├── styles.css      # Dark theme tokens & animations
│   │   └── app.js          # WebSocket client & trace viewer logic
│   ├── models/             # SQLAlchemy async ORM models
│   ├── orchestrator/       # Pipeline graph, task execution & state machine
│   │   ├── graph.py        # Pipeline execution engine, topological executor & broadcaster
│   │   └── review_gate.py  # Review gate evaluation, run_with_retry & critique injection
│   ├── sandbox/            # Docker container isolation & tools
│   ├── schemas/            # Pydantic validation schemas
│   │   ├── architecture.py # Phase 1 Pydantic contracts (ElevatedSpec, FeatureSet, etc.)
│   │   └── graph.py        # ProjectGraph & GraphNode contracts
│   ├── tools/              # Code quality, AST analysis, security scanning tools
│   │   └── ast_export_extractor.py # Python AST & TS/JS export extractor
│   ├── tracing/            # Agent thinking trace system
│   │   └── tracer.py       # PipelineTracer & AgentTrace data structures
│   ├── config.py           # Centralized Pydantic settings & AGENT_MODEL_MAP
│   ├── database.py         # Async database connection pool
│   ├── logging.py          # Structlog JSON logging setup
│   ├── main.py             # FastAPI entry point
│   └── token_tracker.py    # LLM token & pricing tracker
├── output/                 # Output directory for generated code & traces
├── tests/                  # Pytest unit & integration suite
│   ├── test_schemas.py     # Schema & dependency validation tests
│   └── test_graph_executor.py # Topological sorting & cycle handling tests
├── run_pipeline.py         # Standalone CLI pipeline runner
├── pyproject.toml          # Project configuration & dependencies
├── CLAUDE.md               # Coding standards & development rules
├── NEW_PLAN.md             # Graph pipeline specification
└── README.md               # Project documentation
```

---

## 📄 License & Standards

This project follows the strict code quality guidelines specified in [`CLAUDE.md`](file:///c:/Users/ffmou/Downloads/software_builder/ai-software-builder-agent/CLAUDE.md):
- Modular single-responsibility files under 150 lines.
- Functions under 30 lines with single responsibility.
- Strict token budgeting and error recovery.

Distributed under the MIT License. See `LICENSE` for details.
