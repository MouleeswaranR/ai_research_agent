"""
Full pipeline smoke test with SELF-EVALUATING LOOP.
Uses the ACTUAL agents with their real prompts.
Code Generator → Code Reviewer → (fail? → inject_critique → regenerate) → pass
Skips Docker sandbox – writes files locally via a direct LLM code generation step.
"""

import asyncio
import os
import json

from dotenv import load_dotenv
load_dotenv(override=True)

db_url = os.getenv("DATABASE_URL", "")
if db_url.startswith("postgresql://"):
    os.environ["DATABASE_URL"] = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

from app.agents.base import PipelineContext, AgentOutput
from app.agents.product_strategist import ProductStrategistAgent
from app.agents.project_manager import ProjectManagerAgent
from app.agents.system_architect import SystemArchitectAgent
from app.agents.security_architect import SecurityArchitectAgent
from app.agents.planner import PlannerAgent
from app.agents.code_reviewer import CodeReviewerAgent
from app.orchestrator.review_gate import inject_critique, should_retry
from app.agents.llm_client import call_groq_json
from app.logging import setup_logging, get_logger

logger = get_logger("smoke_test")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "calculator")
MAX_REVIEW_LOOPS = 3


async def code_generator_local(context: PipelineContext) -> AgentOutput:
    """Uses the real Code Generator agent's prompt style, but outputs files
    as JSON instead of writing via sandbox tools (since Docker may not be available).
    The agent's actual system prompt and critique injection are preserved.
    """
    from app.agents.code_generator import CodeGeneratorAgent

    # Instantiate the real agent to get its actual identity
    real_agent = CodeGeneratorAgent()
    real_agent.logger.info("generating_code", project_id=context.project_id)

    # Build prompt using the agent's real context-building approach
    critique_text = real_agent._format_critique(context)

    user_prompt = (
        f"Tech Spec:\n{context.tech_spec[:2000]}\n\n"
        f"Architecture:\n{context.architecture[:1500]}\n\n"
        "Implement all modules as files. Output as JSON with filenames as keys "
        "and full file contents as values."
    )
    if critique_text:
        user_prompt += critique_text

    # Call LLM with real agent identity and token budget
    result = await call_groq_json(
        [
            {"role": "system", "content": (
                "You are an expert Python backend developer. Implement the code based on the tech spec.\n"
                "Rules:\n"
                "- Write modular, production-ready code\n"
                "- Add proper error handling and logging\n"
                "- Follow best practices and clean code principles\n"
                "- Output JSON: {filename: file_content}\n"
                "- Include ALL files needed for a working application"
            )},
            {"role": "user", "content": user_prompt},
        ],
        agent_name=real_agent.name,
        max_tokens=real_agent.max_tokens,
    )

    code_files = result.get("data", {})
    if isinstance(code_files, dict):
        context.code_files = code_files

    content = json.dumps({"files": list(code_files.keys())}) if isinstance(code_files, dict) else str(code_files)

    return AgentOutput(
        agent_name=real_agent.name,
        artifact_type="code",
        content=content,
        metadata={"file_count": len(code_files) if isinstance(code_files, dict) else 0},
    )


async def code_reviewer_local(context: PipelineContext) -> AgentOutput:
    """Uses the real Code Reviewer agent's prompt and scoring logic,
    but reviews the code from context.code_files instead of sandbox tools.
    """
    real_reviewer = CodeReviewerAgent()
    real_reviewer.logger.info("review_gate", project_id=context.project_id, stage=context.current_stage)

    # Build code summary for review
    code_dump = "\n".join(
        f"### {fname}\n```\n{content[:1500]}\n```"
        for fname, content in context.code_files.items()
    )

    # Use the real reviewer's LLM call with its actual system prompt style
    from app.config import settings
    verdict = await real_reviewer.call_llm(
        system_prompt=(
            "You are a strict code reviewer. Analyze the code and produce a JSON verdict.\n"
            "Be extremely concise.\n"
            "JSON keys: pass (bool), issues[] (each: {severity, file, line, message, category}), "
            "scores: {security (0-100), quality (0-100), coverage (0-100), complexity (0-100), "
            "maintainability (0-100)}, summary (1 sentence), blocking_issues_count (int)"
        ),
        user_prompt=(
            f"Stage: {context.current_stage}\n\n"
            f"Code to review:\n{code_dump}\n\n"
            f"Thresholds: coverage≥{settings.coverage_threshold}%, "
            f"complexity≤{settings.complexity_threshold}, "
            f"security_block={settings.security_severity_block}\n\n"
            "Produce review verdict."
        ),
        json_mode=True,
    )

    passed = verdict.get("pass", False) if isinstance(verdict, dict) else False
    content = json.dumps(verdict, indent=2) if isinstance(verdict, dict) else str(verdict)

    return AgentOutput(
        agent_name=real_reviewer.name,
        artifact_type="review",
        content=content,
        metadata={
            "passed": passed,
            "scores": verdict.get("scores", {}) if isinstance(verdict, dict) else {},
            "stage": context.current_stage,
        },
        success=passed,
    )


def save_files(code_files: dict[str, str]) -> None:
    """Write generated files to disk."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for filename, content in code_files.items():
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"   📄 {filename} ({len(content)} chars)")


async def main():
    setup_logging()
    print("\n" + "=" * 60)
    print("  AUTO DEV COMPANY – PIPELINE + SELF-EVAL LOOP")
    print("  Using ACTUAL agents with real prompts")
    print(f"  Max review retries: {MAX_REVIEW_LOOPS}")
    print("=" * 60 + "\n")

    idea = (
        "Build a simple calculator web page using only HTML, CSS, and JavaScript. "
        "Support +, -, *, / with a clean dark-themed UI. Single page, no frameworks."
    )
    context = PipelineContext(project_id="calc-003", idea=idea)

    # ── Phase 1: Planning Agents ──────────────────────────────
    agents = [
        ("🎯", "Product Strategist", ProductStrategistAgent(), "prd", 600),
        ("📊", "Project Manager", ProjectManagerAgent(), None, 500),
        ("🏗️ ", "System Architect", SystemArchitectAgent(), "architecture", 600),
        ("🛡️ ", "Security Architect", SecurityArchitectAgent(), "security_spec", 500),
        ("👨‍💻", "Planner", PlannerAgent(), "tech_spec", 600),
    ]

    for emoji, name, agent, attr, tokens in agents:
        print(f"{emoji} {name} ({agent.name})...")
        agent.max_tokens = tokens
        output = await agent.run(context)
        if attr:
            setattr(context, attr, output.content)
        print(f"   ✅ Done ({len(output.content)} chars)\n")

    # ── Phase 2: Self-Evaluating Code Generation Loop ─────────
    print("=" * 60)
    print("  🔄 SELF-EVALUATING LOOP: Code Generator ↔ Code Reviewer")
    print("=" * 60 + "\n")

    context.current_stage = "code_generation"

    for attempt in range(1, MAX_REVIEW_LOOPS + 1):
        # ── Generate ──────────────────────────────────────────
        print(f"🧑‍💻 [Attempt {attempt}/{MAX_REVIEW_LOOPS}] Code Generator running...")
        gen_output = await code_generator_local(context)
        if context.code_files:
            save_files(context.code_files)
            print(f"   ✅ Generated {len(context.code_files)} files\n")
        else:
            print(f"   ⚠️ No files generated, retrying...\n")
            context.review_critiques.append("No files were generated. Ensure output is JSON with filenames as keys.")
            context.retry_count += 1
            continue

        # ── Review (using real Code Reviewer agent) ───────────
        print(f"🔍 [Attempt {attempt}/{MAX_REVIEW_LOOPS}] Code Reviewer (GATE)...")
        review_output = await code_reviewer_local(context)
        passed = review_output.metadata.get("passed", False)
        scores = review_output.metadata.get("scores", {})

        try:
            verdict = json.loads(review_output.content)
            summary_text = verdict.get("summary", "N/A")
            issues = verdict.get("issues", [])
        except (json.JSONDecodeError, TypeError):
            summary_text = "Parse error"
            issues = []

        if passed:
            print(f"   ✅ PASSED: {summary_text}")
            print(f"   Scores: {json.dumps(scores)}\n")
            break
        else:
            print(f"   ❌ FAILED: {summary_text}")
            print(f"   Scores: {json.dumps(scores)}")
            if issues:
                for issue in issues[:5]:
                    if isinstance(issue, dict):
                        print(f"     - [{issue.get('severity', '?')}] {issue.get('file', '?')}: {issue.get('message', '')}")

            # Use REAL review_gate.inject_critique
            if should_retry(context):
                context = inject_critique(context, review_output)
                print(f"\n   🔄 Critique injected → retrying (attempt {context.retry_count}/{MAX_REVIEW_LOOPS})\n")
            else:
                print(f"\n   ⛔ Max retries reached. Escalate to human review.\n")
                break

    # ── Token Summary ─────────────────────────────────────────
    from app.token_tracker import token_tracker
    summary = token_tracker.summary()
    print("=" * 60)
    print("  TOKEN USAGE SUMMARY")
    print("=" * 60)
    print(f"  Total LLM calls:    {summary['total_calls']}")
    print(f"  Input tokens:       {summary['total_input_tokens']}")
    print(f"  Output tokens:      {summary['total_output_tokens']}")
    print(f"  Estimated cost:     ${summary['total_cost_usd']:.4f}")
    print()
    for name, data in summary.get("per_agent", {}).items():
        print(f"    {name}: {data['calls']} calls, "
              f"{data['input_tokens']}in+{data['output_tokens']}out, ${data['cost_usd']:.4f}")
    print("=" * 60)
    print(f"\n📁 Output: {os.path.abspath(OUTPUT_DIR)}")
    print("\n✅ Pipeline complete!")


if __name__ == "__main__":
    asyncio.run(main())
