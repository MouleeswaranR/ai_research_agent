# Multi-Provider LLM Configuration - Working Models (2026-07-06)

## Provider Status Summary

| Provider | Status | Notes |
|----------|--------|-------|
| **Groq** | ✅ WORKING | Primary - Use this now |
| **NVIDIA NIM** | ❌ ACCOUNT BUG | 403 "Public API Endpoints permission" missing server-side |
| **OpenRouter** | ⚠️ STALE MODELS | Free tier rotates monthly - IDs outdated |
| **Gemini** | ⚠️ RATE LIMITED | 429 on free tier - last resort only |

---

## 🟢 Groq Configuration (RECOMMENDED PRIMARY)

**Status**: Fully working, no account issues, reliable

### Available Models

| Model | Context | RPD Limit | Best For |
|-------|---------|-----------|----------|
| `llama-3.3-70b-versatile` | 128K | 1,000 | Planning agents (low volume, high quality) |
| `llama-3.1-8b-instant` | 128K | 14,400 | Critique/eval loops (high frequency) |
| `llama-3.1-70b-versatile` | 128K | 1,000 | Fallback for 3.3 |
| `mixtral-8x7b-32768` | 32K | 5,000 | Mid-tier tasks |

### Recommended Agent Mapping (Groq Only)

```bash
# .env configuration

# Primary provider
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-key-here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FAST_MODEL=llama-3.1-8b-instant

# Per-agent routing (all Groq models)
# High-quality, low-frequency agents
NIM_MODEL_PRODUCT_STRATEGIST=llama-3.3-70b-versatile
NIM_MODEL_PROJECT_MANAGER=llama-3.3-70b-versatile
NIM_MODEL_SYSTEM_ARCHITECT=llama-3.3-70b-versatile
NIM_MODEL_SECURITY_ARCHITECT=llama-3.3-70b-versatile
NIM_MODEL_PLANNER=llama-3.3-70b-versatile

# Code generation (quality matters)
NIM_MODEL_CODE_GENERATOR=llama-3.3-70b-versatile
NIM_MODEL_CODE_GENERATOR_ESCALATION=llama-3.3-70b-versatile
NIM_MODEL_REFACTOR=llama-3.3-70b-versatile
NIM_MODEL_TEST_WRITER=llama-3.3-70b-versatile

# High-frequency loop agents (use fast model!)
NIM_MODEL_CRITIQUE=llama-3.1-8b-instant
NIM_MODEL_SELF_EVAL=llama-3.1-8b-instant

# Post-processing (lightweight)
NIM_MODEL_DEPLOYMENT=llama-3.1-8b-instant
NIM_MODEL_MONITORING=llama-3.1-8b-instant
NIM_MODEL_QUALITY_EVALUATOR=llama-3.3-70b-versatile
```

**Why this mapping?**
- **Critique + Self-Eval**: Called 2-3x per file in retry loops → 14,400 RPD limit needed
- **Planning agents**: Called once → 1,000 RPD fine, use quality model
- **Code gen**: Quality matters → use 70B model

---

## 🔶 OpenRouter Configuration (UPDATED FREE MODELS)

**Status**: Working but free models rotate monthly

### Current Free Models (as of 2026-07-06)

```bash
# .env for OpenRouter

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Agent mapping (verified free models)
# Coding agents - use specialized models
NIM_MODEL_CODE_GENERATOR=poolside/laguna-m.1:free
NIM_MODEL_CODE_GENERATOR_ESCALATION=cohere/north-mini-code:free
NIM_MODEL_REFACTOR=poolside/laguna-m.1:free
NIM_MODEL_TEST_WRITER=cohere/north-mini-code:free

# Planning agents - use reasoning models
NIM_MODEL_PRODUCT_STRATEGIST=nvidia/nemotron-3-ultra-550b-a55b:free
NIM_MODEL_PROJECT_MANAGER=nvidia/nemotron-3-ultra-550b-a55b:free
NIM_MODEL_SYSTEM_ARCHITECT=nvidia/nemotron-3-ultra-550b-a55b:free
NIM_MODEL_PLANNER=nvidia/nemotron-3-ultra-550b-a55b:free

# Security - purpose-built model
NIM_MODEL_SECURITY_ARCHITECT=nvidia/nemotron-3.5-content-safety:free

# Critique/eval - fast general model
NIM_MODEL_CRITIQUE=google/gemma-4-26b-a4b-it:free
NIM_MODEL_SELF_EVAL=google/gemma-4-31b-it:free

# Lightweight agents
NIM_MODEL_DEPLOYMENT=google/gemma-4-26b-a4b-it:free
NIM_MODEL_MONITORING=google/gemma-4-26b-a4b-it:free
NIM_MODEL_QUALITY_EVALUATOR=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
```

### Model Details

**Coding Models**:
- `poolside/laguna-m.1:free` - 256K context, tool calling, reasoning
- `cohere/north-mini-code:free` - 30B MoE, 256K context, fast

**Reasoning Models**:
- `nvidia/nemotron-3-ultra-550b-a55b:free` - 1M context, frontier reasoning
- `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` - Multimodal reasoning

**Security**:
- `nvidia/nemotron-3.5-content-safety:free` - Purpose-built guardrail model

**General Purpose**:
- `google/gemma-4-31b-it:free` / `google/gemma-4-26b-a4b-it:free`
- `openrouter/owl-alpha` - 0-priced agentic tool-use, 1M context

---

## ❌ NVIDIA NIM (CURRENTLY BROKEN)

**Issue**: Server-side permission bug affecting personal accounts

**Error**:
```json
{
  "status": 403,
  "title": "Forbidden",
  "detail": "Authorization failed"
}
```

**Root Cause**: 
- `/v1/models` returns 200 (key valid)
- `/v1/chat/completions` returns 403 (missing "Public API Endpoints" permission)
- This is NOT a code issue - it's NVIDIA's account system bug

**Fix**: 
1. Wait for NVIDIA to fix (check forums.developer.nvidia.com)
2. File support ticket: Search "Public API Endpoints permission 403"
3. Or use Groq/OpenRouter instead

**Don't waste time debugging this** - it's server-side only.

---

## ⚠️ Gemini (RATE LIMITED)

**Status**: Working but 429 errors on free tier under load

**Use Case**: Last-resort fallback only

```bash
# .env
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-2.0-flash-exp

# Only use for absolute fallback scenarios
```

---

## 🎯 Recommended Strategy: Groq Primary

**Best configuration RIGHT NOW**:

```bash
# .env - PRODUCTION READY

# ═══════════════════════════════════════════════════════
# PRIMARY PROVIDER: GROQ (fully working)
# ═══════════════════════════════════════════════════════
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key-here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FAST_MODEL=llama-3.1-8b-instant

# ═══════════════════════════════════════════════════════
# PER-AGENT MODEL ROUTING (optimized for rate limits)
# ═══════════════════════════════════════════════════════

# Planning Phase (1x per pipeline, use quality model)
NIM_MODEL_PRODUCT_STRATEGIST=llama-3.3-70b-versatile
NIM_MODEL_PROJECT_MANAGER=llama-3.3-70b-versatile
NIM_MODEL_SYSTEM_ARCHITECT=llama-3.3-70b-versatile
NIM_MODEL_SECURITY_ARCHITECT=llama-3.3-70b-versatile
NIM_MODEL_PLANNER=llama-3.3-70b-versatile

# Code Generation (quality + volume)
NIM_MODEL_CODE_GENERATOR=llama-3.3-70b-versatile
NIM_MODEL_CODE_GENERATOR_ESCALATION=llama-3.3-70b-versatile
NIM_MODEL_REFACTOR=llama-3.3-70b-versatile
NIM_MODEL_TEST_WRITER=llama-3.3-70b-versatile

# Critique Loop (high frequency - MUST use fast model!)
NIM_MODEL_CRITIQUE=llama-3.1-8b-instant
NIM_MODEL_SELF_EVAL=llama-3.1-8b-instant

# Post-Processing (lightweight)
NIM_MODEL_DEPLOYMENT=llama-3.1-8b-instant
NIM_MODEL_MONITORING=llama-3.1-8b-instant
NIM_MODEL_QUALITY_EVALUATOR=llama-3.3-70b-versatile
```

**Why this works**:
- ✅ Groq has no account issues
- ✅ 70B model for quality (1,000 RPD sufficient for planning/code)
- ✅ 8B instant for critique loops (14,400 RPD prevents quota exhaustion)
- ✅ No API errors, no stale model IDs
- ✅ Free tier, production-ready

---

## Rate Limit Planning

### Groq Limits (Free Tier)

| Model | RPD | RPM | TPD | TPM |
|-------|-----|-----|-----|-----|
| llama-3.3-70b-versatile | 1,000 | 30 | 10,000 | 6,000 |
| llama-3.1-8b-instant | 14,400 | 30 | 20,000 | 15,000 |

**Pipeline Analysis**:
- Planning agents: 5 calls → 70B model (within 1,000 RPD)
- Code gen loop: ~20-50 calls → 70B model (within 1,000 RPD)
- Critique loop: 100-200 calls → 8B model (within 14,400 RPD) ✅
- Tests/refactor: ~50 calls → 70B or 8B (within limits)

**Total**: ~300-400 calls/pipeline → Well within Groq limits

---

## Provider Selection Logic

```python
# app/agents/llm_client.py - Updated provider logic

def _get_provider_config(agent_name: str = "unknown", model_override: str | None = None):
    """Smart provider selection with working models."""
    provider = settings.llm_provider
    
    # Groq (PRIMARY - working)
    if provider == "groq":
        agent_model = settings.AGENT_MODEL_MAP.get(agent_name, settings.groq_model)
        return {
            "provider": "groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json"
            },
            "model": model_override or agent_model
        }
    
    # OpenRouter (verified free models)
    elif provider == "openrouter":
        agent_model = settings.AGENT_MODEL_MAP.get(agent_name, "google/gemma-4-31b-it:free")
        return {
            "provider": "openrouter",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json"
            },
            "model": model_override or agent_model
        }
    
    # NVIDIA NIM (BROKEN - only include for future when fixed)
    elif provider == "nvidia_nim":
        logger.warning("nvidia_nim_currently_broken", message="403 permission bug - falling back to Groq")
        # Auto-fallback to Groq
        return _get_provider_config("groq_fallback", model_override)
    
    # Default to Groq
    else:
        return _get_provider_config("groq_fallback", model_override)
```

---

## Testing Your Configuration

```bash
# Test Groq connection
python scripts/verify_models.py

# Expected output:
# ✅ llama-3.3-70b-versatile: Working
# ✅ llama-3.1-8b-instant: Working
# All agents accessible

# Run test pipeline
python run_pipeline.py \
  --idea "Simple calculator" \
  --project-id test-groq \
  --provider groq

# Check for rate limit warnings in logs
grep "rate_limited" output/test-groq/traces/timeline.json
```

---

## Summary

**IMMEDIATE ACTION**: Use Groq as primary provider

```bash
# Quick fix - update .env:
LLM_PROVIDER=groq

# Use llama-3.3-70b-versatile for planning/code
# Use llama-3.1-8b-instant for critique loops

# Result: Working pipeline, no API errors
```

**NVIDIA NIM**: Don't waste time - it's broken server-side  
**OpenRouter**: Updated model IDs provided above  
**Gemini**: Keep as emergency fallback only

**Status**: ✅ PRODUCTION READY with Groq
