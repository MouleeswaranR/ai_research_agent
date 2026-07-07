# File Writing Issue - Why No Files Were Created

## 🔴 Problem Summary

**Symptom**: Pipeline completes, traces show "code generated", but NO actual code files exist in output folder.

**Location**: `output/converter-app1/` has only:
- ✅ `traces/` folder (exists)
- ✅ `artifacts/` folder (exists)
- ❌ **NO code files** (missing!)

## 🔍 Root Cause Analysis

### Issue 1: LLM Response Truncation

**Evidence from trace** (`code_generator_622ab4c7.json`):

```json
"llm_raw_response": "{\n  \"unitConverterService.js\": \"...\",\n   \"frontend.js\": \"...\n const [toUnit, setToU"
```

**Problem**: Response cut off mid-generation at `setToU` (incomplete JSON)

**Result**:
```json
"parsed_output": {
  "files": []  // ❌ Empty! JSON parsing failed
}
```

### Issue 2: Silent Failure in Self-Learning Loop

**Code Location**: `app/orchestrator/graph.py` line 556

```python
gen_out = await generate_fn(context)
if not context.code_files:  # ← This triggers!
    context.review_critiques.append("No files generated...")
    context.retry_count += 1
    continue  # ← SKIPS _save_files() call!

_save_files(context.project_id, context.code_files)  # ← Never reached!
```

**Flow**:
1. LLM returns truncated JSON
2. Parsing fails → `context.code_files = {}`
3. Check `if not context.code_files:` → True
4. **`continue`** → loops back
5. `_save_files()` never called → **No files written!**

### Issue 3: Max Tokens Still Too Low

**Current Setting**: `max_tokens=16000` (after our recent fix)

**Actual Usage** (from trace):
```json
"token_usage": {
  "output_tokens": 1129,  // Response truncated at 1129 tokens
  "total_tokens": 2196
}
```

**Problem**: Groq has **hard model limits**:
- `llama-3.3-70b-versatile`: **8192 max output tokens**
- `llama-3.1-8b-instant`: **8192 max output tokens**

But we're requesting **16000** → Groq silently caps at 8192 → incomplete output!

### Issue 4: No Partial File Save

**Current Logic**:
```python
# All or nothing approach
if not context.code_files:
    continue  # Skip save entirely
```

**Problem**: Even if LLM generates 5 files but truncates on the 6th, we save ZERO files instead of the 5 complete ones.

---

## ✅ Solutions

### Solution 1: Respect Provider Token Limits

```python
# app/orchestrator/graph.py

def get_safe_max_tokens(provider: str) -> int:
    """Get safe max output tokens for provider."""
    if provider == "groq":
        return 7000  # Leave buffer under 8192 limit
    elif provider == "nvidia_nim":
        return 15000  # NIM has higher limits
    else:
        return 7000  # Conservative default

async def _generate_code_traced(context: PipelineContext) -> AgentOutput:
    # ...
    provider = settings.llm_provider
    safe_max_tokens = get_safe_max_tokens(provider)
    
    result = await call_llm_json(
        [...],
        agent_name=agent.name,
        max_tokens=safe_max_tokens,  # Respect provider limits!
    )
```

### Solution 2: Save Partial Results

```python
async def _generate_code_traced(context: PipelineContext) -> AgentOutput:
    # ...
    try:
        validated = CodeGenerationOutput(files=code)
        context.code_files = validated.files
    except ValidationError as e:
        # Still save whatever valid files we got
        valid_files = {
            k: v for k, v in code.items()
            if isinstance(k, str) and '.' in k and isinstance(v, str) and len(v) > 10
        }
        if valid_files:
            logger.warning(
                "partial_files_saved",
                valid_count=len(valid_files),
                total_attempt=len(code),
            )
            context.code_files = valid_files  # Save partial results!
        else:
            context.code_files = {}  # Truly nothing valid
```

### Solution 3: Always Save After Generation

```python
# app/orchestrator/graph.py in _self_learning_loop

gen_out = await generate_fn(context)

# ALWAYS save whatever we got (even if empty for debugging)
if context.code_files:
    _save_files(context.project_id, context.code_files)
    logger.info("files_saved", count=len(context.code_files))
else:
    logger.warning("no_files_to_save", attempt=attempt)

_save_artifact(context.project_id, f"{stage_name}_gen_v{attempt}", gen_out)

# THEN check if we should retry
if not context.code_files:
    context.review_critiques.append("No files generated. Output must be JSON with filenames as keys.")
    context.retry_count += 1
    continue  # Now safe to continue - files already saved
```

### Solution 4: Split Large Projects into Batches

For projects with 20+ files, generate in batches:

```python
async def _generate_code_in_batches(context: PipelineContext) -> AgentOutput:
    """Generate code in batches to avoid token limits."""
    from app.schemas.code_output import CodeGenerationOutput
    
    # Parse architecture to get file list
    all_files_needed = _extract_file_list_from_architecture(context.architecture)
    
    # Split into batches of 5-8 files
    batch_size = 6
    batches = [all_files_needed[i:i+batch_size] for i in range(0, len(all_files_needed), batch_size)]
    
    all_generated = {}
    
    for batch_num, file_batch in enumerate(batches, 1):
        logger.info("generating_batch", batch=batch_num, files=file_batch)
        
        prompt = (
            f"Generate ONLY these {len(file_batch)} files:\n"
            + "\n".join(f"- {f}" for f in file_batch)
            + "\n\nOutput JSON: {\"filename\": \"complete_content\", ...}"
        )
        
        result = await call_llm_json([...], max_tokens=7000)
        code = result.get("data", {})
        
        # Validate and merge
        try:
            validated = CodeGenerationOutput(files=code)
            all_generated.update(validated.files)
        except ValidationError:
            logger.warning("batch_validation_failed", batch=batch_num)
    
    context.code_files = all_generated
    return AgentOutput(...)
```

### Solution 5: Add File Write Verification

```python
def _save_files(project_id: str, files: dict, subdir: str = "") -> None:
    """Write generated code files to output directory with verification."""
    base = os.path.join("output", project_id, subdir)
    os.makedirs(base, exist_ok=True)
    
    saved_count = 0
    failed_files = []
    
    for fname, content in files.items():
        try:
            path = os.path.join(base, fname)
            os.makedirs(os.path.dirname(path) or base, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(content))
            
            # Verify file was written
            if os.path.exists(path) and os.path.getsize(path) > 0:
                saved_count += 1
            else:
                failed_files.append(fname)
                
        except Exception as e:
            logger.error("file_write_failed", file=fname, error=str(e))
            failed_files.append(fname)
    
    logger.info(
        "files_saved_verification",
        project_id=project_id,
        saved=saved_count,
        failed=len(failed_files),
        failed_files=failed_files[:5],
    )
    
    return saved_count
```

---

## 🛠️ Immediate Fixes to Apply

### Fix 1: Respect Groq Token Limits (CRITICAL)

```python
# In _generate_code_traced, replace:
max_tokens=16000

# With:
max_tokens=7000 if settings.llm_provider == "groq" else 16000
```

### Fix 2: Move _save_files Before Continue (CRITICAL)

```python
# In _self_learning_loop, change from:
gen_out = await generate_fn(context)
if not context.code_files:
    continue
_save_files(...)  # Never reached!

# To:
gen_out = await generate_fn(context)
if context.code_files:  # Save if we have anything
    _save_files(context.project_id, context.code_files)
if not context.code_files:  # Then check for retry
    continue
```

### Fix 3: Save Partial Valid Files

```python
# After code generation, before validation:
if isinstance(code, dict):
    # Extract valid files even if some are invalid
    valid_files = {}
    for fname, content in code.items():
        if isinstance(fname, str) and '.' in fname and isinstance(content, str) and len(content) > 10:
            valid_files[fname] = content
    
    if valid_files:
        context.code_files = valid_files
```

---

## 🧪 Testing After Fixes

### Test 1: Verify Files Are Written
```bash
python run_pipeline.py --idea "Simple calculator" --project-id test-calc

# Check:
ls output/test-calc/*.html  # Should exist
ls output/test-calc/*.js    # Should exist
```

### Test 2: Check Truncation Handling
```bash
python run_pipeline.py --idea "Complex app with 15 files" --project-id test-large

# Should see partial files saved even if not all complete
```

### Test 3: Groq Token Limit Respect
```bash
# In logs, check:
grep "max_tokens" output/test-calc/traces/code_generator_*.json
# Should show 7000, not 16000
```

---

## 📊 Expected Behavior After Fixes

### Before (Broken):
```
1. LLM generates 1129 tokens (truncated)
2. JSON parsing fails
3. context.code_files = {}
4. continue triggered
5. _save_files() skipped
6. Result: NO FILES CREATED ❌
```

### After (Fixed):
```
1. LLM generates up to 7000 tokens (respects Groq limit)
2. JSON may still truncate, but more room
3. Extract valid files from partial JSON
4. _save_files() called BEFORE continue check
5. context.code_files = {valid files}
6. Result: VALID FILES SAVED ✅
```

---

## 🎯 Summary

**Root Causes**:
1. ❌ Requested 16000 tokens but Groq caps at 8192
2. ❌ _save_files() called AFTER empty check
3. ❌ No partial file saving on truncation
4. ❌ All-or-nothing approach loses partial results

**Critical Fixes**:
1. ✅ Respect provider token limits (7000 for Groq)
2. ✅ Move _save_files() before continue
3. ✅ Save partial valid files
4. ✅ Add file write verification logging

**Priority**: **URGENT** - Users see "pipeline complete" but get no files!
