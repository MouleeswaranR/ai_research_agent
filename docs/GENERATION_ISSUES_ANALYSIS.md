# Code Generation Issues - Root Cause Analysis & Solutions

## 🔴 Issues Identified in converter-app Output

### 1. Files Without Extensions
```
output/converter-app/filename
output/converter-app/content
output/converter-app/tests
```

**Root Cause**: LLM returning malformed JSON
```json
// Wrong format returned by LLM:
{
  "filename": "index.html",
  "content": "<html>...</html>"
}

// Should be:
{
  "index.html": "<html>...</html>",
  "styles.css": "body {...}"
}
```

### 2. Incomplete File Content
**Root Cause**: LLM response truncated or returning metadata instead of actual code
- `tests` file contains JSON metadata about tests, not actual test code
- `content` file contains object structure instead of file content
- `filename` just says "improved_content"

### 3. Flat File Structure (No Proper Organization)
```
converter-app/
├── index.html          ✓ OK
├── styles.css          ✓ OK
├── main.js             ✓ OK
├── package.json        ✓ OK
├── sw.js               ✓ OK
├── ConverterComponent.js  ⚠️ Should be in src/components/
├── UnitService.js         ⚠️ Should be in src/services/
├── LocalStorage.js        ⚠️ Should be in src/utils/
├── github-actions.yml     ⚠️ Should be in .github/workflows/
└── tests                  ❌ Wrong format - should be test files
```

**Root Cause**: System Architect not generating proper file tree structure, Planner Agent not enforcing folder hierarchy.

---

## 🔍 Root Causes Deep Dive

### Issue 1: LLM Prompt Ambiguity

**Current Prompt** (`_generate_code_traced`):
```python
"Output ONLY valid JSON: {\"filename\": \"full_file_content\", ...}"
```

**Problem**: This is ambiguous. LLMs sometimes interpret this as:
```json
// Interpretation A (wrong):
[
  {"filename": "index.html", "content": "..."},
  {"filename": "styles.css", "content": "..."}
]

// Interpretation B (correct):
{
  "index.html": "...",
  "styles.css": "..."
}
```

### Issue 2: No Output Schema Validation

**Current Code**:
```python
result = await call_llm_json(...)
code = result.get("data", {})
if isinstance(code, dict):
    context.code_files = code  # No structure validation!
```

**Problem**: 
- Doesn't validate keys are filenames with extensions
- Doesn't validate values are strings (not nested objects)
- Doesn't check for required files (index.html, package.json, etc.)

### Issue 3: File Save Logic Doesn't Handle Nested Paths

**Current Code** (`_save_files` in graph.py):
```python
def _save_files(project_id: str, files: dict, subdir: str = "") -> None:
    base = os.path.join("output", project_id, subdir)
    os.makedirs(base, exist_ok=True)
    for fname, content in files.items():
        path = os.path.join(base, fname)
        os.makedirs(os.path.dirname(path) or base, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(content))
```

**Problem**: If LLM returns flat filenames, this creates flat structure. No enforcement of proper directory hierarchy.

### Issue 4: Max Tokens Too Low

**Current Setting**: `agent.max_tokens = 2048` (default)

**Problem**: 
- Generating 10-20 files needs ~10k-30k tokens
- Token limit causes truncation mid-generation
- Result: incomplete files, malformed JSON

### Issue 5: No Retry on Malformed Output

**Current Flow**:
```python
code = result.get("data", {})
if isinstance(code, dict):
    context.code_files = code  # Accepts ANY dict!
```

**Problem**: Even if LLM returns `{"error": "...", "message": "..."}`, it's accepted as valid code.

---

## ✅ Solutions

### Solution 1: Strict Output Schema with Pydantic

Create `app/schemas/code_output.py`:

```python
from pydantic import BaseModel, field_validator, Field
from typing import Dict

class CodeGenerationOutput(BaseModel):
    """Validated code generation output."""
    
    files: Dict[str, str] = Field(
        description="Map of filepath to file content. Keys must include file extensions."
    )
    
    @field_validator('files')
    @classmethod
    def validate_filenames(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Ensure all keys are valid filenames with extensions."""
        for filename, content in v.items():
            # Must have extension
            if '.' not in filename and not filename.startswith('.'):
                raise ValueError(f"Filename '{filename}' missing extension")
            
            # Content must be string
            if not isinstance(content, str):
                raise ValueError(f"Content for '{filename}' must be string, got {type(content)}")
            
            # Content must not be empty
            if not content.strip():
                raise ValueError(f"Content for '{filename}' is empty")
        
        return v
    
    @field_validator('files')
    @classmethod
    def require_html_for_web_projects(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Web projects must have index.html."""
        has_html = any(f.endswith('.html') for f in v.keys())
        has_js = any(f.endswith(('.js', '.ts', '.jsx', '.tsx')) for f in v.keys())
        
        if has_js and not has_html:
            raise ValueError("Web project must include at least one .html file")
        
        return v
```

### Solution 2: Improved Prompt with Examples

**New Prompt**:
```python
system_prompt = """You are an expert developer. Implement complete, working code from the tech spec.

CRITICAL OUTPUT FORMAT:
You MUST output valid JSON with this EXACT structure:
{
  "path/to/file1.ext": "full file content here",
  "path/to/file2.ext": "full file content here"
}

RULES:
1. Keys = file paths with extensions (e.g., "src/App.js", "index.html")
2. Values = complete file content as strings
3. Include proper folder structure in paths
4. NO nested objects, NO arrays
5. NO metadata fields like "filename", "description"

EXAMPLE (HTML/JS project):
{
  "index.html": "<!DOCTYPE html>\\n<html>...full content...</html>",
  "styles.css": "body { margin: 0; }...full content...",
  "src/main.js": "console.log('hello');...full content...",
  "package.json": "{\\"name\\":\\"project\\"}...full content..."
}

WRONG EXAMPLES (DO NOT DO THIS):
❌ [{"filename": "index.html", "content": "..."}]
❌ {"files": [{"name": "index.html", "code": "..."}]}
❌ {"filename": "index.html", "content": "..."}
"""
```

### Solution 3: Post-Generation Validation & Retry

```python
async def _generate_code_traced(context: PipelineContext) -> AgentOutput:
    """Code generation with validation and retry."""
    agent = CodeGeneratorAgent()
    max_retries = 3
    
    for attempt in range(max_retries):
        prompt = _build_code_prompt(context, attempt)
        
        result = await call_llm_json(
            [
                {"role": "system", "content": STRICT_CODE_GEN_PROMPT},
                {"role": "user", "content": prompt},
            ],
            agent_name=agent.name,
            max_tokens=16000,  # Increased from 2048!
        )
        
        code = result.get("data", {})
        
        # Validate with Pydantic
        try:
            validated = CodeGenerationOutput(files=code)
            context.code_files = validated.files
            
            logger.info(
                "code_generation_success",
                project_id=context.project_id,
                file_count=len(validated.files),
                attempt=attempt + 1,
            )
            
            return AgentOutput(
                agent_name=agent.name,
                artifact_type="code",
                content=json.dumps({"files": list(validated.files.keys())}),
                metadata={"file_count": len(validated.files)},
            )
        
        except ValidationError as e:
            error_msg = f"[validation_error] {e}"
            logger.warning(
                "code_generation_invalid",
                project_id=context.project_id,
                attempt=attempt + 1,
                error=str(e),
            )
            
            if attempt < max_retries - 1:
                # Add error feedback to prompt for next attempt
                context.review_critiques.append(error_msg)
            else:
                raise ValueError(f"Code generation failed after {max_retries} attempts: {e}")
    
    raise ValueError("Code generation failed - max retries exceeded")
```

### Solution 4: Enforce File Structure from Architecture

**Update System Architect Agent**:
```python
# In system_architect.py
file_tree_prompt = """
Design a PROPER file structure with folders:

For HTML/CSS/JS projects:
/
├── index.html
├── styles.css
├── src/
│   ├── components/
│   ├── utils/
│   └── services/
├── tests/
└── package.json

For Python projects:
/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── utils/
├── tests/
└── requirements.txt

Always use proper directory nesting!
"""
```

### Solution 5: Increase Token Limits Per Agent

```python
# In run_pipeline() or agent initialization
planning_agents = [
    (ProductStrategistAgent(), "prd", 1024),
    (ProjectManagerAgent(), None, 1024),
    (SystemArchitectAgent(), "architecture", 2048),
    (SecurityArchitectAgent(), "security_spec", 1024),
    (PlannerAgent(), "tech_spec", 2048),
]

# Code Generator needs much higher limit!
code_generator = CodeGeneratorAgent()
code_generator.max_tokens = 16000  # Was 2048 - too small!

test_writer = TestWriterAgent()
test_writer.max_tokens = 12000  # Was 2048 - too small!
```

### Solution 6: File Structure Post-Processor

```python
def organize_file_structure(files: Dict[str, str], project_type: str = "web") -> Dict[str, str]:
    """Reorganize flat file structure into proper hierarchy."""
    organized = {}
    
    for filepath, content in files.items():
        # Already has path structure
        if '/' in filepath or '\\' in filepath:
            organized[filepath] = content
            continue
        
        # Organize based on file type
        filename = filepath
        
        if filename == 'index.html' or filename.endswith('.html'):
            organized[filename] = content
        
        elif filename == 'styles.css' or filename.endswith('.css'):
            organized[filename] = content
        
        elif filename == 'package.json':
            organized[filename] = content
        
        elif filename.endswith('Component.js') or filename.endswith('Component.jsx'):
            organized[f'src/components/{filename}'] = content
        
        elif filename.endswith('Service.js') or filename.endswith('API.js'):
            organized[f'src/services/{filename}'] = content
        
        elif filename.endswith('Utils.js') or 'Storage' in filename:
            organized[f'src/utils/{filename}'] = content
        
        elif filename.startswith('test_') or filename.endswith('.test.js'):
            organized[f'tests/{filename}'] = content
        
        elif filename.endswith('.test.js') or filename.endswith('.spec.js'):
            organized[f'tests/{filename}'] = content
        
        elif filename.endswith('.yml') or filename.endswith('.yaml'):
            if 'github' in filename or 'actions' in filename:
                organized[f'.github/workflows/{filename}'] = content
            else:
                organized[filename] = content
        
        else:
            # Default to src/ for code files
            if filename.endswith(('.js', '.ts', '.jsx', '.tsx', '.py')):
                organized[f'src/{filename}'] = content
            else:
                organized[filename] = content
    
    return organized
```

---

## 🛠️ Implementation Priority

### Priority 1 (Critical - Fixes Broken Output):
1. ✅ **Increase max_tokens** to 16000 for CodeGenerator
2. ✅ **Add CodeGenerationOutput schema** with validation
3. ✅ **Update system prompt** with explicit examples
4. ✅ **Add retry logic** on validation failure

### Priority 2 (Important - Improves Structure):
5. ⚠️ **Add file structure post-processor**
6. ⚠️ **Update System Architect prompts** for proper folder structure
7. ⚠️ **Add file existence checks** (require index.html for web projects)

### Priority 3 (Enhancement - Better UX):
8. 🔵 **Add progress indicators** for large file generations
9. 🔵 **Better error messages** with examples of correct format
10. 🔵 **Generate README.md** with project structure explanation

---

## 📊 Expected Improvements

### Before (Current):
```
output/converter-app/
├── index.html              ✓
├── styles.css              ✓
├── ConverterComponent.js   ✓
├── filename                ❌ Malformed
├── content                 ❌ Malformed
├── tests                   ❌ Not actual test files
└── ... 15 flat files
```

### After (Fixed):
```
output/converter-app/
├── index.html
├── styles.css
├── package.json
├── README.md
├── src/
│   ├── main.js
│   ├── components/
│   │   └── ConverterComponent.js
│   ├── services/
│   │   └── UnitService.js
│   └── utils/
│       └── LocalStorage.js
├── tests/
│   ├── ConverterComponent.test.js
│   ├── UnitService.test.js
│   └── LocalStorage.test.js
└── .github/
    └── workflows/
        └── ci.yml
```

---

## 🧪 Testing Strategy

### Test 1: Simple Project (2-3 files)
```bash
python run_pipeline.py --idea "Simple HTML calculator"
```
**Expected**: Clean structure, all files valid

### Test 2: Medium Project (10-15 files)
```bash
python run_pipeline.py --idea "Todo app with localStorage"
```
**Expected**: Proper src/ structure, complete files

### Test 3: Complex Project (20+ files)
```bash
python run_pipeline.py --idea "E-commerce product catalog with cart"
```
**Expected**: Nested folders, no truncation

---

## 🔧 Quick Fixes to Apply Now

### 1. Update Code Generator Max Tokens
```python
# In app/orchestrator/graph.py, _generate_code_traced():
result = await call_llm_json(
    [...],
    agent_name=agent.name,
    max_tokens=16000,  # Changed from 2048
)
```

### 2. Add Output Validation
```python
# Check if keys are valid filenames
for filename in code.keys():
    if '.' not in filename:
        logger.error("invalid_filename", name=filename)
        # Retry generation
```

### 3. Filter Invalid Files Before Save
```python
# In _save_files():
valid_files = {
    fname: content 
    for fname, content in files.items()
    if '.' in fname and isinstance(content, str) and len(content) > 10
}
_save_files(project_id, valid_files)
```

---

## 📝 Summary

**Root Causes**:
1. Ambiguous prompts leading to malformed JSON
2. No output validation (accepts any dict)
3. Token limits too low (2048 → need 16000+)
4. No file structure enforcement
5. No retry on malformed output

**Quick Wins**:
- Increase max_tokens to 16000
- Add Pydantic schema validation
- Improve system prompt with explicit examples
- Add retry logic on validation errors

**Result**: Clean, organized, complete code generation with proper folder structure.
