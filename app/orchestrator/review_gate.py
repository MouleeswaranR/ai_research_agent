"""Review gate – blocking review logic with retry routing and schema-generic retry."""

from __future__ import annotations

import asyncio
import json

from pydantic import ValidationError

from app.agents import get_agent
from app.agents.base import AgentOutput, PipelineContext
from app.config import settings
from app.logging import get_logger

logger = get_logger("review_gate")


class MaxRetriesExceeded(Exception):
    """Raised when an agent fails to produce valid output within max retries."""

    def __init__(self, agent_name: str, last_error: str | None = None) -> None:
        self.agent_name = agent_name
        self.last_error = last_error
        super().__init__(f"Max retries exceeded for agent '{agent_name}'. Last error: {last_error}")


async def run_review_gate(
    context: PipelineContext,
) -> tuple[bool, AgentOutput]:
    """Execute the Code Reviewer Agent as a blocking gate."""
    reviewer = get_agent("code_reviewer")

    logger.info(
        "review_gate_start",
        project_id=context.project_id,
        stage=context.current_stage,
        attempt=context.retry_count + 1,
    )

    output = await reviewer.run(context)
    passed = output.metadata.get("passed", False)

    logger.info(
        "review_gate_result",
        project_id=context.project_id,
        stage=context.current_stage,
        passed=passed,
        scores=output.metadata.get("scores", {}),
    )

    return passed, output


def should_retry(context: PipelineContext) -> bool:
    """Check if we should retry the producing stage."""
    return context.retry_count < settings.review_max_retries


def inject_critique(context: PipelineContext, review_output: AgentOutput) -> PipelineContext:
    """Inject review critique into context for the producing agent's retry."""
    try:
        verdict = json.loads(review_output.content)
        critique_text = f"Review attempt {context.retry_count + 1} FAILED.\n"
        critique_text += f"Summary: {verdict.get('summary', 'N/A')}\n"
        issues = verdict.get("issues", [])
        if issues:
            critique_text += "Issues to fix:\n"
            for issue in issues[:10]:
                if isinstance(issue, dict):
                    critique_text += (
                        f"  - [{issue.get('severity', '?')}] {issue.get('file', '?')}:"
                        f"{issue.get('line', '?')} – {issue.get('message', '')}\n"
                    )
                else:
                    critique_text += f"  - {issue}\n"
        context.review_critiques.append(critique_text)
    except (json.JSONDecodeError, AttributeError):
        context.review_critiques.append(f"Review failed. Raw: {review_output.content[:500]}")

    context.retry_count += 1
    return context


async def run_with_retry(
    generator_agent,
    critique_agent,
    self_eval_agent,
    context,
    schema,
    max_retries: int = 3,
    use_sandbox: bool = False,
):
    """Schema-generic retry loop with Pydantic and semantic validation.
    
    If use_sandbox=True, runs sandbox verification (linting, security, tests)
    and feeds real errors back as last_error instead of pure LLM critique.
    """
    from app.sandbox.code_verifier import verify_code_in_sandbox

    last_error = None
    agent_name = getattr(generator_agent, "name", "unknown")

    for attempt in range(1, max_retries + 1):
        if hasattr(generator_agent, "generate"):
            res = generator_agent.generate(context, previous_error=last_error)
            raw = await res if asyncio.iscoroutine(res) else res
        elif hasattr(generator_agent, "run_with_trace"):
            if isinstance(context, PipelineContext):
                out = await generator_agent.run_with_trace(context)
            else:
                ctx = PipelineContext(project_id="graph-node", idea=str(context))
                out = await generator_agent.run_with_trace(ctx)
            raw = out.content
        else:
            out = await generator_agent.run(context)
            raw = out.content

        try:
            parsed = schema.model_validate_json(raw)
        except (ValidationError, Exception) as e:
            last_error = f"[schema_error] {e}"
            continue

        if hasattr(parsed, "validate_dependency_ids"):
            try:
                parsed.validate_dependency_ids()
            except ValueError as e:
                last_error = f"[semantic_error] {e}"
                continue

        # Run sandbox verification if enabled and we have code files
        if use_sandbox and isinstance(context, PipelineContext) and context.code_files:
            try:
                project_id = getattr(context, "project_id", "unknown")
                verification = verify_code_in_sandbox(project_id, context.code_files)

                if verification.has_blocking_issues():
                    # Build detailed error message from real sandbox results
                    error_parts = []
                    if not verification.syntax_valid:
                        error_parts.append("[SYNTAX ERRORS]\n" + "\n".join(
                            f"  {e['file']}: {e['message']}" for e in verification.lint_errors[:5]
                        ))
                    if verification.security_findings:
                        error_parts.append("[SECURITY ISSUES]\n" + "\n".join(
                            f"  {f['file']}:{f['line']} [{f['severity']}] {f['message']}"
                            for f in verification.security_findings[:5]
                        ))
                    if verification.test_failures:
                        error_parts.append("[TEST FAILURES]\n" + "\n".join(
                            f"  {t.get('test', 'unknown')}: {t.get('message', '')}"
                            for t in verification.test_failures[:5]
                        ))

                    last_error = "[sandbox_verification_failed]\n" + "\n\n".join(error_parts)
                    continue

            except Exception as e:
                logger.warning("sandbox_verification_error", error=str(e))
                # Continue with LLM critique if sandbox fails

        if hasattr(critique_agent, "review"):
            res = critique_agent.review(parsed, context)
            critique = await res if asyncio.iscoroutine(res) else res
        else:
            critique = "Critique completed."

        if hasattr(self_eval_agent, "score"):
            res = self_eval_agent.score(parsed, critique)
            verdict = await res if asyncio.iscoroutine(res) else res
            score_val = getattr(verdict, "score", 0.8)
            verdict_str = getattr(verdict, "verdict", "accept")
            if verdict_str == "accept" and score_val >= 0.75:
                return parsed, verdict
            last_error = f"[critique] {critique} | score={score_val}"
        else:
            return parsed, AgentOutput(agent_name=agent_name, artifact_type="schema", content=raw)

    raise MaxRetriesExceeded(agent_name, last_error)
