"""Pipeline orchestrator – runs full agent pipeline with graph execution support."""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict, deque

from app.agents.base import AgentOutput, PipelineContext
from app.agents.code_generator import CodeGeneratorAgent
from app.agents.critique import CritiqueAgent
from app.agents.deployment import DeploymentAgent
from app.agents.llm_client import call_llm_json
from app.agents.monitoring import MonitoringAgent
from app.agents.planner import PlannerAgent
from app.agents.product_strategist import ProductStrategistAgent
from app.agents.project_manager import ProjectManagerAgent
from app.agents.quality_evaluator import QualityEvaluatorAgent
from app.agents.refactor import RefactorAgent
from app.agents.security_architect import SecurityArchitectAgent
from app.agents.self_evaluator import SelfEvaluationAgent
from app.agents.system_architect import SystemArchitectAgent
from app.agents.test_writer import TestWriterAgent
from app.logging import get_logger
from app.schemas.architecture import NodeType
from app.schemas.graph import NodeStatus, ProjectGraph
from app.token_tracker import token_tracker
from app.tracing.tracer import pipeline_tracer

logger = get_logger("orchestrator.graph")
_event_listeners: list = []


def register_event_listener(callback) -> None:
    """Register a callback for pipeline events."""
    _event_listeners.append(callback)


def unregister_event_listener(callback) -> None:
    """Remove a registered pipeline event callback."""
    if callback in _event_listeners:
        _event_listeners.remove(callback)


async def _broadcast_event(event: dict) -> None:
    """Broadcast pipeline event to listeners and Web Dashboard server."""
    for listener in list(_event_listeners):
        try:
            await listener(event)
        except Exception:
            pass

    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post("http://localhost:8000/api/dashboard/broadcast", json=event)
    except Exception:
        pass


def _safe_str(val, max_len: int = 99999) -> str:
    """Safely convert value to truncated string."""
    if val is None:
        return ""
    if isinstance(val, dict):
        val = json.dumps(val, indent=2)
    return str(val)[:max_len]


def _estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token."""
    return len(text) // 4


def _truncate_dep_context(dep_context: dict, max_tokens: int = 50000) -> dict:
    """Truncate dependency context to fit within token budget.
    
    If full code exceeds limit, falls back to interface-only (exports/imports).
    """
    from app.tools.ast_export_extractor import extract_exports_via_ast

    full_text = "\n\n".join(f"# {path}\n{code}" for path, code in dep_context.items())
    total_tokens = _estimate_tokens(full_text)

    if total_tokens <= max_tokens:
        return dep_context  # Fits, use as-is

    # Fallback: extract signatures only
    logger.warning(
        "dep_context_truncated",
        total_tokens=total_tokens,
        max_tokens=max_tokens,
        fallback="interface_only"
    )

    truncated = {}
    for path, code in dep_context.items():
        # Detect language from extension
        lang = "python" if path.endswith(".py") else "javascript" if path.endswith((".js", ".ts")) else None
        exports = extract_exports_via_ast(code, lang)

        # Build interface-only summary
        interface_lines = [f"# {path} (interface only)"]
        for symbol in exports:
            if symbol.signature:
                interface_lines.append(f"{symbol.kind.value} {symbol.name}: {symbol.signature}")
            else:
                interface_lines.append(f"{symbol.kind.value} {symbol.name}")

        truncated[path] = "\n".join(interface_lines)

    return truncated


def _save_files(project_id: str, files: dict, subdir: str = "") -> None:
    """Write generated code files to output directory."""
    base = os.path.join("output", project_id, subdir)
    os.makedirs(base, exist_ok=True)
    for fname, content in files.items():
        path = os.path.join(base, fname)
        os.makedirs(os.path.dirname(path) or base, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(content))


def _save_artifact(project_id: str, name: str, output: AgentOutput) -> None:
    """Write output artifact JSON to disk."""
    base = os.path.join("output", project_id, "artifacts")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "agent": output.agent_name,
                "type": output.artifact_type,
                "content": output.content,
                "metadata": output.metadata,
            },
            f,
            indent=2,
        )


def compute_generation_levels(graph: ProjectGraph) -> list[list[str]]:
    """Compute topological generation levels for a dependency graph."""
    indegree = {nid: 0 for nid in graph.nodes}
    children = defaultdict(list)
    for nid, node in graph.nodes.items():
        for dep_id in node.depends_on:
            if dep_id not in graph.nodes:
                continue
            children[dep_id].append(nid)
            indegree[nid] += 1

    queue = deque([nid for nid, d in indegree.items() if d == 0])
    levels, seen = [], 0
    while queue:
        level = list(queue)
        levels.append(level)
        queue.clear()
        for nid in level:
            seen += 1
            for child in children[nid]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

    if seen != len(graph.nodes):
        cyclic = [nid for nid, d in indegree.items() if d > 0]
        return handle_cycles(graph, cyclic)
    return levels


def handle_cycles(graph: ProjectGraph, cyclic_ids: list[str]) -> list[list[str]]:
    """Resolve dependency cycles by stubbing weakest node and recomputing."""
    weakest = min(cyclic_ids, key=lambda nid: len(graph.nodes[nid].planned_exports))
    graph.nodes[weakest].status = NodeStatus.STUBBED
    for nid in cyclic_ids:
        node = graph.nodes[nid]
        node.depends_on = [d for d in node.depends_on if d != weakest]
    return compute_generation_levels(graph)


async def execute_graph(
    graph: ProjectGraph,
    tracer,
    rate_limiter,
    code_generator_agent,
    critique_agent,
    self_eval_agent,
):
    """Execute code generation across topological graph levels."""
    from app.orchestrator.review_gate import MaxRetriesExceeded, run_with_retry
    from app.schemas.graph import CodeFileResult
    from app.tools.ast_export_extractor import extract_exports_via_ast

    graph.generation_levels = compute_generation_levels(graph)
    for level in graph.generation_levels:
        tasks = [
            _generate_node(
                graph, nid, tracer, rate_limiter, code_generator_agent,
                critique_agent, self_eval_agent, run_with_retry,
                extract_exports_via_ast, MaxRetriesExceeded, CodeFileResult,
            )
            for nid in level if graph.nodes[nid].type == NodeType.FILE
        ]
        if tasks:
            await asyncio.gather(*tasks)
    return graph


async def _generate_node(
    graph, node_id, tracer, rate_limiter, code_generator_agent,
    critique_agent, self_eval_agent, run_with_retry,
    extract_exports_via_ast, MaxRetriesExceeded, CodeFileResult,
):
    """Generate code for a single graph node with review and export verification."""
    node = graph.nodes[node_id]
    node.status = NodeStatus.IN_PROGRESS

    # Pre-flight: verify all dependencies are ready
    dep_context = {}
    stub_dependencies = []
    missing_dependencies = []

    for imp in node.planned_imports:
        if imp.from_path not in graph.nodes:
            continue  # External import, skip

        dep_node = graph.nodes[imp.from_path]

        if dep_node.status == NodeStatus.STUBBED:
            stub_dependencies.append(imp.from_path)
            dep_context[imp.from_path] = dep_node.generated_code or ""
        elif dep_node.status == NodeStatus.GENERATED:
            dep_context[imp.from_path] = dep_node.generated_code
        else:
            # Dependency not ready (PENDING, IN_PROGRESS, FAILED, BLOCKED)
            missing_dependencies.append((imp.from_path, dep_node.status.value))

    # Fail fast if critical dependencies are missing
    if missing_dependencies:
        node.status = NodeStatus.BLOCKED
        tracer.log_failure(
            node_id,
            reason=f"Dependencies not ready: {missing_dependencies}"
        )
        logger.error(
            "node_blocked_missing_deps",
            node_id=node_id,
            missing=missing_dependencies,
        )
        return

    # Build context with stub warnings
    dep_context = _truncate_dep_context(dep_context, max_tokens=50000)

    context_meta = {
        "node": node,
        "dependency_code": dep_context,
        "stub_dependencies": stub_dependencies,  # Signal to generator
    }

    async with rate_limiter:
        try:
            parsed, _ = await run_with_retry(
                code_generator_agent, critique_agent, self_eval_agent,
                context=context_meta,
                schema=CodeFileResult,
            )
        except MaxRetriesExceeded:
            node.status = NodeStatus.FAILED
            tracer.log_failure(node_id)
            return

    node.generated_code = parsed.code
    node.actual_exports = extract_exports_via_ast(parsed.code, node.language)
    node.status = NodeStatus.GENERATED

    # Check for export drift
    planned_names = {e.name for e in node.planned_exports}
    actual_names = {e.name for e in node.actual_exports}

    if planned_names != actual_names:
        tracer.log_export_drift(node_id, node.planned_exports, node.actual_exports)

        # Update planned_exports to match reality for downstream consumers
        node.planned_exports = node.actual_exports

        # If drift is significant (missing critical exports), mark for retry
        if not planned_names.issubset(actual_names):
            logger.warning(
                "export_drift_missing_planned",
                node_id=node_id,
                missing=planned_names - actual_names,
            )


async def _run_agent_with_trace(agent, context: PipelineContext, attr: str | None = None) -> AgentOutput:
    """Execute a single agent with tracing and event broadcasting."""
    await _broadcast_event({
        "type": "agent_started",
        "agent": agent.name,
        "stage": context.current_stage,
    })

    output = await agent.run_with_trace(context)
    if attr:
        setattr(context, attr, output.content)

    await _broadcast_event({
        "type": "agent_completed",
        "agent": agent.name,
        "stage": context.current_stage,
        "content_length": len(output.content),
    })

    return output


async def _generate_code_traced(context: PipelineContext) -> AgentOutput:
    """Code generation with tracing – produces {filename: content} via LLM with validation."""
    from pydantic import ValidationError

    from app.schemas.code_output import CodeGenerationOutput

    agent = CodeGeneratorAgent()
    max_retries = 3

    # Respect provider token limits
    provider = settings.llm_provider
    if provider == "groq":
        safe_max_tokens = 7000  # Groq caps at 8192, leave buffer
    elif provider == "nvidia_nim":
        safe_max_tokens = 15000  # NIM has higher limits
    else:
        safe_max_tokens = 7000  # Conservative default

    for attempt in range(1, max_retries + 1):
        prompt = (
            f"Tech Spec:\n{_safe_str(context.tech_spec, 3000)}\n\n"
            f"Architecture:\n{_safe_str(context.architecture, 2000)}\n\n"
            "Implement ALL files with COMPLETE content."
        )
        if context.review_critiques:
            prompt += "\n\n## CRITICAL FIXES REQUIRED:\n" + "\n\n".join(context.review_critiques[-3:])

        trace = pipeline_tracer.start_trace(agent.name, context.current_stage, attempt)
        trace.add_step("prompt_built", f"Code generation attempt {attempt} ({len(prompt)} chars)")

        result = await call_llm_json(
            [
                {"role": "system", "content": (
                    "You are an expert developer. Implement complete, working code from the tech spec.\n\n"
                    "CRITICAL OUTPUT FORMAT - You MUST output valid JSON with this EXACT structure:\n"
                    "{\n"
                    '  "path/to/file1.ext": "full file content here",\n'
                    '  "path/to/file2.ext": "full file content here"\n'
                    "}\n\n"
                    "RULES:\n"
                    "1. Keys = file paths with extensions (e.g., 'src/App.js', 'index.html')\n"
                    "2. Values = complete file content as strings (not truncated!)\n"
                    "3. Include proper folder structure in paths (src/, tests/, etc.)\n"
                    "4. NO nested objects, NO arrays, NO metadata fields\n"
                    "5. Each file must be 100% complete and working\n\n"
                    "EXAMPLE (HTML/JS project):\n"
                    "{\n"
                    '  "index.html": "<!DOCTYPE html>\\n<html>...FULL CONTENT...</html>",\n'
                    '  "styles.css": "body { margin: 0; }...FULL CONTENT...",\n'
                    '  "src/main.js": "console.log(\'hello\');...FULL CONTENT...",\n'
                    '  "package.json": "{\\"name\\":\\"project\\"}...FULL CONTENT..."\n'
                    "}\n\n"
                    "WRONG (DO NOT DO THIS):\n"
                    '❌ [{"filename": "index.html", "content": "..."}]\n'
                    '❌ {"filename": "index.html", "content": "..."}\n'
                    '❌ {"files": [...]}'
                )},
                {"role": "user", "content": prompt},
            ],
            agent_name=agent.name,
            max_tokens=safe_max_tokens,  # Respect provider limits!
        )

        code = result.get("data", {})

        # First, try to extract ANY valid files (partial save on truncation)
        valid_files = {}
        if isinstance(code, dict):
            for fname, content in code.items():
                if isinstance(fname, str) and '.' in fname and isinstance(content, str) and len(content) > 10:
                    valid_files[fname] = content

        # Then validate with strict schema
        try:
            validated = CodeGenerationOutput(files=code)
            context.code_files = validated.files

            file_counts = validated.get_file_count_by_type()
            trace.parsed_output = {
                "files": list(validated.files.keys()),
                "file_count": len(validated.files),
                "file_types": file_counts,
            }
            trace.add_step("code_validated", f"Generated {len(validated.files)} valid files: {file_counts}")
            pipeline_tracer.end_trace(agent.name, success=True)

            logger.info(
                "code_generation_success",
                project_id=context.project_id,
                file_count=len(validated.files),
                attempt=attempt,
            )

            return AgentOutput(
                agent_name=agent.name,
                artifact_type="code",
                content=json.dumps({"files": list(validated.files.keys())}),
                metadata={"file_count": len(validated.files), "attempt": attempt},
            )

        except ValidationError as e:
            # Validation failed, but save partial valid files if we have them
            if valid_files:
                logger.warning(
                    "partial_files_saved",
                    project_id=context.project_id,
                    valid_count=len(valid_files),
                    total_attempted=len(code),
                    attempt=attempt,
                )
                context.code_files = valid_files  # Save partial results!
            else:
                context.code_files = {}

            error_msg = f"[validation_error_attempt_{attempt}] {str(e)[:300]}"
            logger.warning(
                "code_generation_invalid",
                project_id=context.project_id,
                attempt=attempt,
                error=str(e)[:200],
            )

            trace.add_step("validation_failed", f"Attempt {attempt} failed: {str(e)[:200]}")
            pipeline_tracer.end_trace(agent.name, success=False, error=str(e)[:100])

            if attempt < max_retries:
                # Add specific error feedback for next attempt
                context.review_critiques.append(
                    f"PREVIOUS ATTEMPT {attempt} FAILED:\n"
                    f"{error_msg}\n\n"
                    f"You MUST output valid JSON: {{\"filename.ext\": \"content\", ...}}\n"
                    f"NO arrays, NO nested objects, NO metadata fields!"
                )
            else:
                # Final attempt failed - return whatever we have
                logger.error(
                    "code_generation_failed_all_attempts",
                    project_id=context.project_id,
                    retries=max_retries,
                    partial_files=len(context.code_files),
                )

                return AgentOutput(
                    agent_name=agent.name,
                    artifact_type="code",
                    content=json.dumps({
                        "files": list(context.code_files.keys()),
                        "error": "validation_failed",
                        "partial_save": len(context.code_files) > 0
                    }),
                    metadata={
                        "file_count": len(context.code_files),
                        "validation_failed": True,
                        "partial_save": len(context.code_files) > 0
                    },
                )

    # Should never reach here, but just in case
    return AgentOutput(
        agent_name=agent.name,
        artifact_type="code",
        content=json.dumps({"files": [], "error": "max_retries_exceeded"}),
        metadata={"file_count": 0},
    )


async def _write_tests_traced(context: PipelineContext) -> AgentOutput:
    """Test writing with tracing – produces test files via LLM with validation."""
    from pydantic import ValidationError

    from app.schemas.code_output import CodeGenerationOutput

    agent = TestWriterAgent()
    trace = pipeline_tracer.start_trace(agent.name, context.current_stage, context.retry_count + 1)

    code_summary = "\n".join(
        f"### {p}\n```\n{c[:600]}\n```" for p, c in list(context.code_files.items())[:8]
    )

    result = await call_llm_json(
        [
            {"role": "system", "content": (
                "Write comprehensive tests. Output JSON: {\"filename.test.ext\": \"test_content\", ...}\n"
                "Use pytest for Python, Jest/Mocha for JS.\n"
                "Keys must include .test. or .spec. in filename.\n"
                "Values must be complete test files with imports, test cases, assertions."
            )},
            {"role": "user", "content": f"Code:\n{code_summary}\n\nWrite comprehensive tests for all major functions/classes."},
        ],
        agent_name=agent.name,
        max_tokens=12000,  # Increased from 2048
    )

    tests = result.get("data", {})

    # Validate test output
    try:
        if isinstance(tests, dict):
            validated = CodeGenerationOutput(files=tests)
            context.test_files = validated.files
            trace.parsed_output = {"test_files": list(validated.files.keys())}
        else:
            context.test_files = tests if isinstance(tests, dict) else {}
            trace.parsed_output = {"test_files": list(tests.keys()) if isinstance(tests, dict) else []}
    except ValidationError as e:
        logger.warning("test_validation_failed", error=str(e)[:200])
        context.test_files = tests if isinstance(tests, dict) else {}
        trace.parsed_output = {"test_files": list(tests.keys()) if isinstance(tests, dict) else [], "validation_warning": str(e)[:100]}

    pipeline_tracer.end_trace(agent.name, success=True)

    return AgentOutput(
        agent_name=agent.name,
        artifact_type="test",
        content=json.dumps({"test_files": list(context.test_files.keys())}),
        metadata={"test_count": len(context.test_files)},
    )


async def _refactor_traced(context: PipelineContext) -> AgentOutput:
    """Refactoring with tracing – improves code via LLM."""
    agent = RefactorAgent()
    trace = pipeline_tracer.start_trace(agent.name, context.current_stage, context.retry_count + 1)

    code_dump = "\n".join(f"### {f}\n```\n{c}\n```" for f, c in context.code_files.items())

    result = await call_llm_json(
        [
            {"role": "system", "content": (
                "Refactor the code. Apply DRY, SOLID. Don't change functionality.\n"
                "Output JSON: {\"filename\": \"improved_content\", ...}"
            )},
            {"role": "user", "content": f"Refactor:\n{code_dump}"},
        ],
        agent_name=agent.name,
        max_tokens=agent.max_tokens,
    )

    refactored = result.get("data", {})
    if isinstance(refactored, dict):
        context.code_files.update(refactored)

    trace.parsed_output = {"files": list(refactored.keys()) if isinstance(refactored, dict) else []}
    pipeline_tracer.end_trace(agent.name, success=True)

    return AgentOutput(
        agent_name=agent.name,
        artifact_type="refactor",
        content=json.dumps({"files": list(refactored.keys()) if isinstance(refactored, dict) else []}),
    )


async def _self_learning_loop(
    context: PipelineContext,
    generate_fn,
    stage_name: str,
    max_retries: int = 3,
) -> bool:
    """Self-learning loop: Generate → Critique → Self-Evaluate."""
    critique_agent = CritiqueAgent()
    eval_agent = SelfEvaluationAgent()
    context.current_stage = stage_name

    for attempt in range(1, max_retries + 1):
        await _broadcast_event({
            "type": "loop_attempt",
            "stage": stage_name,
            "attempt": attempt,
            "max_retries": max_retries,
        })

        gen_out = await generate_fn(context)

        # ALWAYS save files if we got any (even partial results)
        if context.code_files:
            _save_files(context.project_id, context.code_files)
            logger.info(
                "files_saved",
                project_id=context.project_id,
                file_count=len(context.code_files),
                attempt=attempt,
            )
        else:
            logger.warning(
                "no_files_generated",
                project_id=context.project_id,
                attempt=attempt,
            )

        _save_artifact(context.project_id, f"{stage_name}_gen_v{attempt}", gen_out)

        # THEN check if we should retry
        if not context.code_files:
            context.review_critiques.append("No files generated. Output must be JSON with filenames as keys.")
            context.retry_count += 1
            continue
        await asyncio.sleep(2)

        critique_out = await critique_agent.run_with_trace(context)
        _save_artifact(context.project_id, f"{stage_name}_critique_v{attempt}", critique_out)

        try:
            crit = json.loads(critique_out.content)
        except (json.JSONDecodeError, TypeError):
            crit = {}

        quality = crit.get("overall_quality", 0)
        items = crit.get("critique_items", [])
        ready = crit.get("ready_for_review", False)

        await _broadcast_event({
            "type": "critique_result",
            "stage": stage_name,
            "attempt": attempt,
            "quality": quality,
            "issues": len(items),
            "ready": ready,
        })

        eval_out = await eval_agent.run_with_trace(context)
        _save_artifact(context.project_id, f"{stage_name}_eval_v{attempt}", eval_out)
        await asyncio.sleep(2)

        decision = eval_out.metadata.get("decision", "escalate")

        await _broadcast_event({
            "type": "self_eval_decision",
            "stage": stage_name,
            "attempt": attempt,
            "decision": decision,
            "improvement_score": eval_out.metadata.get("improvement_score", 0),
        })

        if decision == "accept":
            return True
        elif decision == "improve" and attempt < max_retries:
            critique_text = _build_critique_feedback(attempt, quality, items, eval_out)
            context.review_critiques.append(critique_text)
            context.retry_count += 1
        else:
            return False

    return False


def _build_critique_feedback(attempt: int, quality: int, items: list, eval_out: AgentOutput) -> str:
    """Format critique items into feedback text for the next retry."""
    feedback = eval_out.metadata.get("feedback", "")
    critique_text = f"Attempt {attempt} critique (quality={quality}/100):\n"
    for item in items[:5]:
        if isinstance(item, dict):
            critique_text += (
                f"- [{item.get('severity', '?')}] "
                f"{item.get('file', '?')}: {item.get('description', '')}\n"
            )
    if feedback:
        critique_text += f"\nSelf-evaluator feedback: {feedback}\n"
    return critique_text


class _DummyLimiter:
    """Async context manager stub for rate limiting."""
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


async def run_pipeline(project_id: str, idea: str, max_retries: int = 3) -> dict:
    """Execute the complete multi-agent pipeline with tracing."""
    from app.config import settings
    from app.logging import setup_logging

    setup_logging()
    pipeline_tracer.reset(pipeline_id=project_id)
    token_tracker.reset()

    context = PipelineContext(project_id=project_id, idea=idea)
    os.makedirs(os.path.join("output", project_id), exist_ok=True)

    await _broadcast_event({"type": "pipeline_started", "project_id": project_id})

    # ── Phase 1: Planning Agents ─────────────────────────────
    planning_agents = [
        (ProductStrategistAgent(), "prd", 600),
        (ProjectManagerAgent(), None, 500),
        (SystemArchitectAgent(), "architecture", 600),
        (SecurityArchitectAgent(), "security_spec", 500),
        (PlannerAgent(), "tech_spec", 600),
    ]

    for agent, attr, tokens in planning_agents:
        agent.max_tokens = tokens
        context.current_stage = agent.name
        output = await _run_agent_with_trace(agent, context, attr)
        _save_artifact(project_id, agent.name, output)
        await asyncio.sleep(2)

    # ── Phase 2: Code Generation ─────────────────────────────
    context.retry_count = 0
    context.review_critiques = []

    if settings.ENABLE_GRAPH_PIPELINE:
        try:
            pg = ProjectGraph.model_validate_json(context.tech_spec)
            pg.validate_consistency()  # Verify planned_imports match depends_on
            await execute_graph(
                pg, pipeline_tracer, _DummyLimiter(),
                CodeGeneratorAgent(), CritiqueAgent(), SelfEvaluationAgent()
            )
            context.code_files = {
                nid: n.generated_code for nid, n in pg.nodes.items() if n.generated_code
            }
        except Exception as err:
            logger.error("graph_execution_failed", error=str(err))
            await _self_learning_loop(context, _generate_code_traced, "code_generation", max_retries)
    else:
        await _self_learning_loop(context, _generate_code_traced, "code_generation", max_retries)

    # ── Phase 3: Test Writing ────────────────────────────────
    context.retry_count = 0
    context.review_critiques = []
    await _self_learning_loop(context, _write_tests_traced, "test_writing", max_retries)
    if context.test_files:
        _save_files(project_id, context.test_files)

    # ── Phase 4: Refactoring ─────────────────────────────────
    context.retry_count = 0
    context.review_critiques = []
    await _self_learning_loop(context, _refactor_traced, "refactoring", max_retries)
    _save_files(project_id, context.code_files)

    # ── Phase 5: Post-Coding Agents ──────────────────────────
    post_agents = [
        (DeploymentAgent(), "deployment"),
        (MonitoringAgent(), "monitoring"),
        (QualityEvaluatorAgent(), "quality_eval"),
    ]

    for agent, stage_name in post_agents:
        context.current_stage = stage_name
        try:
            output = await _run_agent_with_trace(agent, context)
            _save_artifact(project_id, agent.name, output)
        except Exception as exc:
            logger.error("post_agent_error", agent=agent.name, error=str(exc))

    if settings.trace_save_to_disk:
        pipeline_tracer.save_to_disk(os.path.join("output", project_id))

    await _broadcast_event({
        "type": "pipeline_completed",
        "project_id": project_id,
        "token_summary": token_tracker.summary(),
        "trace_summary": pipeline_tracer.summary(),
    })

    return {
        "status": "completed",
        "project_id": project_id,
        "token_summary": token_tracker.summary(),
        "trace_summary": pipeline_tracer.summary(),
    }
