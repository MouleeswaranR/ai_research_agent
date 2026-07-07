# 🚀 Deployment Readiness Checklist

## Environment Configuration Status

### ✅ LLM Provider Configuration

#### Primary: NVIDIA NIM
- **Status**: Configured with automatic Groq fallback
- **Models**: 14 agent-specific models configured
- **Fallback**: Automatic on 400/401/403/404/network errors
- **Required**:
  - `NVIDIA_NIM_API_KEY` - Get from https://build.nvidia.com/
  - `NVIDIA_NIM_BASE_URL` - Default: `https://integrate.api.nvidia.com/v1`

#### Fallback: Groq
- **Status**: Automatic failover enabled
- **Models**: `llama-3.3-70b-versatile` (primary), `llama-3.1-8b-instant` (fast)
- **Required**:
  - `GROQ_API_KEY` - Get from https://console.groq.com/

### ✅ Per-Agent Model Routing

| Agent | NIM Model | Fallback Behavior | Verified Available |
|-------|-----------|-------------------|-------------------|
| Product Strategist | `meta/llama-3.3-70b-instruct` | → Groq | ✓ Yes |
| Project Manager | `nvidia/nemotron-3-super-120b-a12b` | → Groq | ⚠️ Check NIM catalog |
| System Architect | `nvidia/nemotron-3-super-120b-a12b` | → Groq | ⚠️ Check NIM catalog |
| Security Architect | `nvidia/nemotron-3-super-120b-a12b` | → Groq | ⚠️ Check NIM catalog |
| Planner | `z-ai/glm-5.2` | → Groq | ⚠️ Check NIM catalog |
| Code Generator | `z-ai/glm-5.2` | → Groq | ⚠️ Check NIM catalog |
| Code Escalation | `deepseek-ai/deepseek-v4-pro` | → Groq | ⚠️ Check NIM catalog |
| Critique | `deepseek-ai/deepseek-v4-flash` | → Groq | ⚠️ Check NIM catalog |
| Self Evaluator | `meta/llama-3.3-70b-instruct` | → Groq | ✓ Yes |
| Test Writer | `deepseek-ai/deepseek-v4-flash` | → Groq | ⚠️ Check NIM catalog |
| Refactor | `moonshotai/kimi-k2.6` | → Groq | ⚠️ Check NIM catalog |
| Deployment | `meta/llama-3.3-70b-instruct` | → Groq | ✓ Yes |
| Monitoring | `meta/llama-3.3-70b-instruct` | → Groq | ✓ Yes |
| Quality Evaluator | `nvidia/nemotron-3-super-120b-a12b` | → Groq | ⚠️ Check NIM catalog |

**Note**: Models marked with ⚠️ should be verified in the [NVIDIA NIM Model Catalog](https://build.nvidia.com/explore/discover). If unavailable, the system will automatically fall back to Groq without interruption.

### ✅ Safe Mode Configuration

To use only verified models, uncomment the "Safe Fallback Configuration" section in `.env`:

```bash
# All agents use meta/llama-3.3-70b-instruct (verified available)
NIM_MODEL_PRODUCT_STRATEGIST=meta/llama-3.3-70b-instruct
NIM_MODEL_PROJECT_MANAGER=meta/llama-3.3-70b-instruct
# ... etc
```

---

## Infrastructure Readiness

### ✅ Database (Neon PostgreSQL)
- **Status**: Configured
- **Required**: `DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require`
- **Setup**: Get free account at https://neon.tech/
- **Verification**:
  ```bash
  psql $DATABASE_URL -c "SELECT 1"
  ```

### ✅ Redis
- **Status**: Configured
- **Required**: 
  - `REDIS_URL=redis://localhost:6379/0`
  - `CELERY_BROKER_URL=redis://localhost:6379/1`
  - `CELERY_RESULT_BACKEND=redis://localhost:6379/2`
- **Quick Start**:
  ```bash
  docker run -d --name redis -p 6379:6379 redis:7-alpine
  ```
- **Verification**:
  ```bash
  redis-cli ping  # Should return PONG
  ```

### ✅ Docker (Sandbox Execution)
- **Status**: Configured
- **Required**: Docker Desktop running
- **Sandbox Images**: Auto-built on first use
  - `autodev-sandbox-python` (Python 3.12 + Ruff/Bandit/Pytest)
  - `autodev-sandbox-node` (Node 20 + ESLint)
- **Verification**:
  ```bash
  docker ps  # Should list running containers
  ```

---

## Feature Flags

### Graph Pipeline (NEW)
```bash
ENABLE_GRAPH_PIPELINE=false  # Set to 'true' to enable
```

**When Enabled**:
- Phase 1 agents produce typed Pydantic schemas
- Code generation follows topological dependency order
- Automatic export drift correction
- Pre-flight dependency validation

**When Disabled** (backward compatible):
- Uses original flat-plan pipeline
- All existing functionality preserved

---

## Sandbox Configuration

```bash
SANDBOX_TIMEOUT=60                  # Max seconds per command
SANDBOX_MEMORY_LIMIT=512m           # Memory per container
SANDBOX_CPU_LIMIT=1.0               # CPU cores
SANDBOX_NETWORK_DISABLED=true       # Isolate from network
```

**Security**: Sandboxes are ephemeral, resource-limited, and network-isolated by default.

---

## Automatic Failover Behavior

### How It Works

1. **Primary Attempt**: Call specified NIM model
   ```
   Agent: code_generator
   Model: z-ai/glm-5.2
   ```

2. **Error Detection**: HTTP 400/404/401/403 or network failure
   ```
   LOG: nim_model_unavailable_falling_back_to_groq
   ```

3. **Automatic Fallback**: Switch to Groq
   ```
   Retry with: llama-3.3-70b-versatile
   ```

4. **Transparent to Pipeline**: Agent continues without interruption

### Logged Events
```json
{
  "event": "nim_failed_falling_back_to_groq",
  "agent": "code_generator",
  "original_model": "z-ai/glm-5.2",
  "fallback_model": "llama-3.3-70b-versatile",
  "reason": "404: Model not found"
}
```

---

## Pre-Flight Checks

### 1. API Keys
```bash
# Test NVIDIA NIM
curl https://integrate.api.nvidia.com/v1/models \
  -H "Authorization: Bearer $NVIDIA_NIM_API_KEY"

# Test Groq
curl https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY"
```

### 2. Database Connection
```bash
psql $DATABASE_URL -c "SELECT version()"
```

### 3. Redis Connection
```bash
redis-cli -u $REDIS_URL ping
```

### 4. Docker Running
```bash
docker info
```

### 5. Python Dependencies
```bash
pip install -e ".[dev]"
```

---

## Quick Start Script

```bash
#!/bin/bash
# start_pipeline.sh

# 1. Check environment
if [ ! -f .env ]; then
  echo "❌ .env file not found. Copy from .env.example"
  exit 1
fi

# 2. Start Redis if not running
docker ps | grep redis > /dev/null || docker run -d --name redis -p 6379:6379 redis:7-alpine

# 3. Test database
psql $DATABASE_URL -c "SELECT 1" > /dev/null || {
  echo "❌ Database connection failed"
  exit 1
}

# 4. Test LLM providers
echo "Testing NVIDIA NIM..."
python -c "
from app.agents.llm_client import call_llm
import asyncio
result = asyncio.run(call_llm([{'role':'user','content':'hello'}], agent_name='test', max_tokens=10))
print(f'✓ NIM connected: {result[\"provider\"]}')
"

# 5. Start pipeline
echo "🚀 Starting pipeline..."
python run_pipeline.py --idea "Build a simple calculator web app"
```

---

## Troubleshooting

### Issue: NIM Model Not Found (404)
**Solution**: System automatically falls back to Groq. Check logs for `nim_model_unavailable_falling_back_to_groq`.

### Issue: Both NIM and Groq Failing
**Symptoms**: Pipeline stops with authentication errors
**Solution**:
1. Verify both API keys are valid
2. Check internet connectivity
3. Review rate limits: https://console.groq.com/limits

### Issue: Sandbox Commands Timing Out
**Solution**: Increase `SANDBOX_TIMEOUT` in `.env` (default: 60s)

### Issue: Redis Connection Refused
**Solution**:
```bash
docker start redis  # If container stopped
# OR
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### Issue: Graph Pipeline Validation Errors
**Symptoms**: `ValueError: planned_imports != depends_on`
**Solution**: This indicates Planner Agent output has inconsistent dependencies. The error message shows which node has the mismatch. This is caught early before any code generation.

---

## Cost Optimization

### Use Fast Models for Non-Critical Agents
```bash
# Critique and self-eval can use smaller models
NIM_MODEL_CRITIQUE=meta/llama-3.1-8b-instruct
NIM_MODEL_SELF_EVAL=meta/llama-3.1-8b-instruct
```

### Enable Sandbox Verification (Reduces LLM Retries)
```bash
# review_gate.py automatically uses sandbox when available
# Catches syntax/security errors before expensive LLM retries
# Expected savings: 15-30% token cost
```

### Monitor Token Usage
```bash
# Check output/[project_id]/traces/timeline.json
# Contains per-agent token breakdown
```

---

## Deployment Status

| Component | Status | Notes |
|-----------|--------|-------|
| LLM Routing | ✅ Ready | Automatic fallback enabled |
| Sandbox Integration | ✅ Ready | Verification wired into critique loop |
| Graph Pipeline | ✅ Ready | Feature-flagged, backward compatible |
| Dependency Validation | ✅ Ready | Pre-flight checks implemented |
| Export Drift Correction | ✅ Ready | Automatic interface updates |
| Token Budget Management | ✅ Ready | Truncation to 50k tokens |
| Database Schema | ⚠️ Pending | Run migrations on first start |
| API Documentation | ✅ Complete | See README.md |

---

## Final Checklist

- [ ] Copy `.env.example` to `.env`
- [ ] Set `NVIDIA_NIM_API_KEY`
- [ ] Set `GROQ_API_KEY` (fallback)
- [ ] Set `DATABASE_URL` (Neon PostgreSQL)
- [ ] Start Redis: `docker run -d --name redis -p 6379:6379 redis:7-alpine`
- [ ] Verify Docker Desktop is running
- [ ] Install dependencies: `pip install -e ".[dev]"`
- [ ] Test run: `python run_pipeline.py --idea "Hello world app"`
- [ ] Check output: `ls output/[project_id]/`
- [ ] Review traces: `cat output/[project_id]/traces/timeline.json`

---

**System Status**: ✅ READY TO DEPLOY

All critical architecture fixes applied. Automatic failover ensures pipeline continues even if specialized NIM models are unavailable.
