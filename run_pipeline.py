"""Auto Dev Company – CLI runner script for the full pipeline.

Executes all 5 phases with Critique + Self-Evaluation loops, token tracking,
and agent thinking trace collection.
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone

from app.config import settings
from app.agents.base import PipelineContext, AgentOutput
from app.tracing.tracer import pipeline_tracer
from app.token_tracker import token_tracker
from app.logging import get_logger
from app.agents.llm_client import call_llm_json

logger = get_logger("run_pipeline")


def _safe_str(val, max_len: int = 99999) -> str:
    """Safely convert a value to string and truncate."""
    if val is None:
        return ""
    if isinstance(val, dict):
        val = json.dumps(val, indent=2)
    return str(val)[:max_len]


# =====================================================================
#  LIGHTWEIGHT WRAPPERS (call real agents by identity, skip sandbox)
# =====================================================================

async def _generate_code(context: PipelineContext) -> AgentOutput:
    """Code Generator: produces {filename: content} via LLM."""
    from app.agents.code_generator import CodeGeneratorAgent
    agent = CodeGeneratorAgent()

    trace = pipeline_tracer.start_trace(agent.name, context.current_stage, context.retry_count + 1)
    trace.add_step("prompt_building", "Building code generation prompt from tech spec and architecture")

    prompt = (
        f"Original User Idea:\n{_safe_str(context.idea, 1000)}\n\n"
        f"Tech Spec:\n{_safe_str(context.tech_spec, 3000)}\n\n"
        f"Architecture:\n{_safe_str(context.architecture, 2000)}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Implement ALL logic fully. NEVER use placeholders (e.g., 'TODO', 'pass', '...').\n"
        "2. Ensure the code is completely working, especially core logic like UI event handlers and data processing.\n"
        "3. Use a proper, multi-file directory structure (e.g., 'public/index.html', 'src/styles.css', 'src/app.js'). DO NOT combine everything into a single monolithic file.\n"
        "Output JSON: {\"path/to/file.ext\": \"content\", ...}"
    )
    if context.review_critiques:
        prompt += "\n\n## MUST FIX (from previous review)\n" + "\n---\n".join(context.review_critiques[-3:])
        trace.add_step("critique_injected", f"Injecting {len(context.review_critiques)} critique(s)")

    result = await call_llm_json(
        [{"role": "system", "content": (
            "You are an expert developer. Implement production-ready code from the tech spec and user idea.\n"
            "Output ONLY valid JSON: {\"path/to/file.ext\": \"full_file_content_with_newlines\", ...}\n"
            "Every generated file must be COMPLETE, FULLY IMPLEMENTED, and free of placeholders or stubs. Ensure strict multi-file modularity."
        )},
         {"role": "user", "content": prompt}],
        agent_name=agent.name, max_tokens=agent.max_tokens,
    )
    
    code = result if isinstance(result, dict) else {}
    if "raw_output" in code:
        logger.error("code_gen_failed", project_id=context.project_id, msg="LLM returned invalid JSON")
        code = {}
        
    if code:
        context.code_files = code
        save_files(context.project_id, code)

    trace.parsed_output = {"files": list(code.keys())}
    trace.add_step("code_generated", f"Generated {len(code)} files")
    pipeline_tracer.end_trace(agent.name)

    return AgentOutput(agent_name=agent.name, artifact_type="code",
                       content=json.dumps({"files": list(code.keys())}),
                       metadata={"file_count": len(code)})


async def _write_tests(context: PipelineContext) -> AgentOutput:
    """Test Writer: produces test files via LLM."""
    from app.agents.test_writer import TestWriterAgent
    agent = TestWriterAgent()

    trace = pipeline_tracer.start_trace(agent.name, context.current_stage, context.retry_count + 1)

    code_summary = "\n".join(f"### {p}\n```\n{c[:600]}\n```" for p, c in list(context.code_files.items())[:8])
    result = await call_llm_json(
        [{"role": "system", "content": "Write tests. Output JSON: {\"tests/test_file.ext\": \"content\", ...}. Use pytest for python, jest for JS."},
         {"role": "user", "content": f"Code:\n{code_summary}\n\nWrite comprehensive tests."}],
        agent_name=agent.name, max_tokens=agent.max_tokens,
    )
    
    tests = result if isinstance(result, dict) else {}
    if "raw_output" in tests:
        tests = {}
        
    if tests:
        context.test_files = tests
        save_files(context.project_id, tests)

    trace.parsed_output = {"test_files": list(tests.keys())}
    pipeline_tracer.end_trace(agent.name)

    return AgentOutput(agent_name=agent.name, artifact_type="test",
                       content=json.dumps({"test_files": list(tests.keys())}))


async def _refactor(context: PipelineContext) -> AgentOutput:
    """Refactor Agent: improves code via LLM."""
    from app.agents.refactor import RefactorAgent
    agent = RefactorAgent()

    trace = pipeline_tracer.start_trace(agent.name, context.current_stage, context.retry_count + 1)

    code_dump = "\n".join(f"### {f}\n```\n{c}\n```" for f, c in context.code_files.items())
    result = await call_llm_json(
        [{"role": "system", "content": (
            "Refactor the code. Apply DRY, SOLID. Don't change functionality.\n"
            "Output JSON: {\"path/to/file.ext\": \"full_refactored_content\", ...}"
        )},
         {"role": "user", "content": f"Refactor:\n{code_dump}"}],
        agent_name=agent.name, max_tokens=agent.max_tokens,
    )
    
    refactored = result if isinstance(result, dict) else {}
    if "raw_output" in refactored:
        refactored = {}
        
    if refactored:
        context.code_files.update(refactored)
        save_files(context.project_id, context.code_files)

    trace.parsed_output = {"files": list(refactored.keys())}
    pipeline_tracer.end_trace(agent.name)

    return AgentOutput(agent_name=agent.name, artifact_type="refactor",
                       content=json.dumps({"files": list(refactored.keys())}))


async def _deployment(context: PipelineContext) -> AgentOutput:
    """Deployment: generates configs via LLM."""
    from app.agents.deployment import DeploymentAgent
    agent = DeploymentAgent()

    trace = pipeline_tracer.start_trace(agent.name, "deployment")

    result = await call_llm_json(
        [{"role": "system", "content": "Generate deployment configs. Output JSON: {dockerfile, docker_compose, ci_pipeline}"},
         {"role": "user", "content": f"Architecture:\n{_safe_str(context.architecture, 1000)}\nFiles: {list(context.code_files.keys())}"}],
        agent_name=agent.name, max_tokens=agent.max_tokens,
    )

    pipeline_tracer.end_trace(agent.name)
    return AgentOutput(agent_name=agent.name, artifact_type="deployment",
                       content=json.dumps(result, indent=2))


async def _monitoring(context: PipelineContext) -> AgentOutput:
    """Monitoring: generates configs via LLM."""
    from app.agents.monitoring import MonitoringAgent
    agent = MonitoringAgent()

    trace = pipeline_tracer.start_trace(agent.name, "monitoring")

    result = await call_llm_json(
        [{"role": "system", "content": "Generate monitoring config. Output JSON: {health_checks[], metrics[], alerting_rules[]}"},
         {"role": "user", "content": f"Architecture:\n{_safe_str(context.architecture, 800)}\nFiles: {list(context.code_files.keys())}"}],
        agent_name=agent.name, max_tokens=agent.max_tokens,
    )

    pipeline_tracer.end_trace(agent.name)
    return AgentOutput(agent_name=agent.name, artifact_type="monitoring",
                       content=json.dumps(result, indent=2))


async def _quality_eval(context: PipelineContext) -> AgentOutput:
    """Quality Evaluator: scores project via LLM."""
    from app.agents.quality_evaluator import QualityEvaluatorAgent
    agent = QualityEvaluatorAgent()

    trace = pipeline_tracer.start_trace(agent.name, "quality_eval")

    code_summary = "\n".join(f"- {f} ({len(c)} chars)" for f, c in context.code_files.items())
    result = await call_llm_json(
        [{"role": "system", "content": (
            "Score project quality. Output JSON: {overall_score: 0-100, "
            "dimensions: {code_quality, security, architecture, maintainability}, "
            "strengths[], improvements[], production_ready: bool, summary}"
        )},
         {"role": "user", "content": f"Project: {context.idea[:200]}\nFiles:\n{code_summary}\nTests: {list(context.test_files.keys())}"}],
        agent_name=agent.name, max_tokens=agent.max_tokens,
    )

    pipeline_tracer.end_trace(agent.name)
    return AgentOutput(agent_name=agent.name, artifact_type="quality_evaluation",
                       content=json.dumps(result, indent=2))


# =====================================================================
#  FILE I/O
# =====================================================================

def save_files(project_id: str, files: dict, subdir: str = "") -> None:
    """Write generated files to the output directory."""
    base = os.path.join("output", project_id, subdir)
    os.makedirs(base, exist_ok=True)
    
    junk_names = {"filename", "content", "tests", "raw_output", "improved_content", "files"}
    
    for fname, content in files.items():
        if not fname or not isinstance(fname, str):
            continue
            
        fname_clean = fname.strip().strip("/")
        if fname_clean.lower() in junk_names:
            logger.warning("skipping_junk_file", project_id=project_id, fname=fname)
            continue
            
        # If it doesn't have an extension, and isn't a known special file like Dockerfile, skip it
        if "." not in fname_clean and fname_clean.lower() not in ("dockerfile", "makefile", "caddyfile", "readme", "license"):
            logger.warning("skipping_extensionless_file", project_id=project_id, fname=fname)
            continue
            
        if not isinstance(content, str):
            logger.warning("skipping_non_string_content", project_id=project_id, fname=fname)
            continue
            
        path = os.path.join(base, fname_clean)
        os.makedirs(os.path.dirname(path) or base, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def save_artifact(project_id: str, name: str, output: AgentOutput) -> None:
    """Write an agent artifact to disk as JSON."""
    base = os.path.join("output", project_id, "artifacts")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"agent": output.agent_name, "type": output.artifact_type,
                    "content": output.content, "metadata": output.metadata}, f, indent=2)


# =====================================================================
#  SELF-LEARNING LOOP
# =====================================================================

async def self_learning_loop(
    context: PipelineContext,
    generate_fn,
    stage_name: str,
    max_retries: int = 3,
) -> bool:
    """Run the self-learning loop for a coding stage."""
    from app.agents.critique import CritiqueAgent
    from app.agents.self_evaluator import SelfEvaluationAgent

    critique_agent = CritiqueAgent()
    self_eval_agent = SelfEvaluationAgent()

    context.current_stage = stage_name

    for attempt in range(max_retries):
        context.retry_count = attempt
        print(f"  [Attempt {attempt + 1}/{max_retries}] Generating...")

        output = await generate_fn(context)
        save_artifact(context.project_id, f"{stage_name}_attempt_{attempt + 1}", output)

        print(f"  [Attempt {attempt + 1}/{max_retries}] Critique Agent analyzing...")
        critique_out = await critique_agent.run_with_trace(context)
        save_artifact(context.project_id, f"critique_{stage_name}_{attempt + 1}", critique_out)

        critique_meta = critique_out.metadata
        print(
            f"    Quality: {critique_meta.get('overall_quality', 0)}/100 | "
            f"Issues: {critique_meta.get('issue_count', 0)} | "
            f"Ready: {critique_meta.get('ready_for_review', False)}"
        )

        print(f"  [Attempt {attempt + 1}/{max_retries}] Self-Evaluation Agent deciding...")
        eval_out = await self_eval_agent.run_with_trace(context)
        save_artifact(context.project_id, f"self_eval_{stage_name}_{attempt + 1}", eval_out)

        decision = eval_out.metadata.get("decision", "improve")
        confidence = eval_out.metadata.get("confidence", 0)
        score = eval_out.metadata.get("improvement_score", 0)

        print(f"    Decision: {decision.upper()} (improvement: {score}/100, confidence: {confidence}/100)")

        if decision == "accept":
            print(f"    >> Accepted at attempt {attempt + 1}!\n")
            return True
        elif decision == "escalate":
            print(f"    >> Escalating: {eval_out.metadata.get('reason', '')}\n")
            return False
        else:
            top = critique_meta.get("top_improvements", [])
            context.review_critiques.extend(top)
            print("    >> Feeding back critique, retrying...\n")

    print(f"    >> ESCALATED / Max retries reached\n")
    return False


# =====================================================================
#  MAIN RUNNER
# =====================================================================

async def main(idea: str, project_id: str, max_retries: int, provider: str) -> None:
    """Run full 5-phase pipeline with Critique + Self-Evaluation loops."""
    if provider:
        settings.llm_provider = provider

    context = PipelineContext(project_id=project_id, idea=idea)
    pipeline_tracer.reset(pipeline_id=project_id)
    token_tracker.reset()

    print("=" * 60)
    print(f"  AUTO DEV COMPANY - FULL PIPELINE")
    print(f"  with Critique + Self-Evaluation Loop + Tracing")
    print(f"  Project: {project_id}")
    print(f"  LLM Provider: {settings.llm_provider}")
    print(f"  Model: {settings.active_model}")
    print(f"  Max retries per stage: {max_retries}")
    print("=" * 60)

    # ============================================================
    # PHASE 1: PLANNING AGENTS
    # ============================================================
    print("\n[PHASE 1] PLANNING AGENTS")
    print("-" * 40)

    from app.agents.product_strategist import ProductStrategistAgent
    from app.agents.project_manager import ProjectManagerAgent
    from app.agents.system_architect import SystemArchitectAgent
    from app.agents.security_architect import SecurityArchitectAgent
    from app.agents.planner import PlannerAgent

    planning_agents = [
        ("Product Strategist", ProductStrategistAgent(), "prd"),
        ("Project Manager", ProjectManagerAgent(), "task_backlog"),
        ("System Architect", SystemArchitectAgent(), "architecture"),
        ("Security Architect", SecurityArchitectAgent(), "security_spec"),
        ("Planner", PlannerAgent(), "tech_spec"),
    ]

    for label, agent, context_attr in planning_agents:
        print(f"  {label} ({agent.name})...")
        output = await agent.run_with_trace(context)
        setattr(context, context_attr, output.content)
        save_artifact(project_id, agent.name, output)
        print(f"    Done ({len(output.content)} chars)\n")

    # ============================================================
    # PHASE 2: CODE GENERATION + SELF-LEARNING LOOP
    # ============================================================
    print("\n[PHASE 2] CODE GENERATION + SELF-LEARNING LOOP")
    print("-" * 40)

    accepted = await self_learning_loop(
        context, _generate_code, "code_generation", max_retries=max_retries
    )
    if not accepted:
        print("  [!] Code generation did not pass self-evaluation.\n")

    if context.code_files:
        save_files(project_id, context.code_files)

    # ============================================================
    # PHASE 3: TEST WRITING + SELF-LEARNING LOOP
    # ============================================================
    print("\n[PHASE 3] TEST WRITING + SELF-LEARNING LOOP")
    print("-" * 40)

    context.retry_count = 0
    context.review_critiques = []

    accepted = await self_learning_loop(
        context, _write_tests, "test_writing", max_retries=max_retries
    )
    if not accepted:
        print("  [!] Test writing did not pass self-evaluation.\n")

    if context.test_files:
        save_files(project_id, context.test_files)

    # ============================================================
    # PHASE 4: REFACTORING + SELF-LEARNING LOOP
    # ============================================================
    print("\n[PHASE 4] REFACTORING + SELF-LEARNING LOOP")
    print("-" * 40)

    context.retry_count = 0
    context.review_critiques = []

    accepted = await self_learning_loop(
        context, _refactor, "refactoring", max_retries=max_retries
    )
    if not accepted:
        print("  [!] Refactoring did not pass self-evaluation.\n")

    if context.code_files:
        save_files(project_id, context.code_files)

    # ============================================================
    # PHASE 5: POST-CODING AGENTS
    # ============================================================
    print("\n[PHASE 5] POST-CODING AGENTS")
    print("-" * 40)

    post = [
        ("Deployment", _deployment),
        ("Monitoring", _monitoring),
        ("Quality Evaluator", _quality_eval),
    ]

    for name, fn in post:
        print(f"  {name}...")
        try:
            output = await fn(context)
            save_artifact(project_id, output.agent_name, output)
            print(f"    Done\n")
        except Exception as e:
            print(f"    Error: {e}\n")

    # ============================================================
    # SAVE TRACES
    # ============================================================
    print("\n[TRACES] Saving agent thinking traces...")
    traces_dir = pipeline_tracer.save_to_disk(os.path.join("output", project_id))
    print(f"  Traces saved to: {traces_dir}")
    print(f"  Total traces: {len(pipeline_tracer.all_traces)}")

    # ============================================================
    # TOKEN SUMMARY
    # ============================================================
    s = token_tracker.summary()
    print("\n" + "=" * 60)
    print("  TOKEN USAGE SUMMARY")
    print("=" * 60)
    print(f"  LLM Provider:     {settings.llm_provider}")
    print(f"  Model:            {settings.active_model}")
    print(f"  Total LLM calls:  {s['total_calls']}")
    print(f"  Input tokens:     {s['total_input_tokens']}")
    print(f"  Output tokens:    {s['total_output_tokens']}")
    print(f"  Cost:             ${s['total_cost_usd']:.4f}")
    print("=" * 60)

    print(f"\n🎉 PIPELINE COMPLETE!")
    print(f"  Files: {os.path.abspath(os.path.join('output', project_id))}")
    print(f"  Traces: {os.path.abspath(traces_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto Dev Company Pipeline")
    parser.add_argument("--idea", type=str, required=True, help="Project idea description")
    parser.add_argument("--project-id", type=str, default="sample-app", help="Unique project identifier")
    parser.add_argument("--max-retries", type=int, default=2, help="Max self-learning retries per stage")
    parser.add_argument("--provider", type=str, default=None, choices=["nvidia_nim", "groq"])
    args = parser.parse_args()

    asyncio.run(main(args.idea, args.project_id, args.max_retries, args.provider))
