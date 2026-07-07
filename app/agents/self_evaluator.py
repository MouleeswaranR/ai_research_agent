"""Self-Evaluation Agent – drives the self-learning loop between coding agents.

Compares the current output against previous attempts, measures improvement,
and decides whether to:
  (a) Accept and proceed to the next stage
  (b) Send back to the producing agent with targeted feedback
  (c) Escalate to human review

This creates a CLOSED-LOOP SELF-IMPROVEMENT CYCLE:
  Code Generator -> Critique -> Self-Evaluation -> (improve? -> back to Generator)
                                                -> (accept? -> next stage)
"""

import json

from app.agents.base import AgentOutput, BaseAgent, PipelineContext


class SelfEvaluationAgent(BaseAgent):
    name = "self_evaluator"
    description = "Drives self-learning loop: compares iterations, measures improvement, decides next action"
    max_tokens = 512

    def __init__(self) -> None:
        super().__init__()
        self.tools = []

    async def run(self, context: PipelineContext) -> AgentOutput:
        def _safe(v, n=99999):
            if v is None: return ""
            if isinstance(v, dict): return json.dumps(v, indent=2)[:n]
            return str(v)[:n]

        self.logger.info(
            "self_evaluating",
            project_id=context.project_id,
            stage=context.current_stage,
            attempt=context.retry_count + 1,
        )

        # Build history of previous critiques for comparison
        critique_history = ""
        if context.review_critiques:
            critique_history = "\n---\n".join(context.review_critiques[-3:])

        code_summary = "\n".join(
            f"- {fname} ({len(_safe(content))} chars)"
            for fname, content in context.code_files.items()
        )

        system_prompt = (
            "You are a self-evaluation engine that drives a self-learning loop.\n"
            "You compare the CURRENT output against PREVIOUS critique feedback.\n\n"
            "Your job:\n"
            "1. Check if previous critique issues were ADDRESSED\n"
            "2. Measure IMPROVEMENT between iterations\n"
            "3. Identify any NEW issues introduced\n"
            "4. Decide the next action\n\n"
            "Output JSON:\n"
            "- decision: 'accept' | 'improve' | 'escalate'\n"
            "- improvement_score: 0-100 (how much better vs previous attempt)\n"
            "- issues_fixed: int (count of previously reported issues now fixed)\n"
            "- issues_remaining: int (count of unresolved issues)\n"
            "- new_issues: int (count of new issues introduced)\n"
            "- feedback_for_agent: string (specific, actionable feedback if decision='improve')\n"
            "- rationale: string (why this decision)\n"
            "- confidence: 0-100 (confidence in the decision)"
        )

        user_prompt = (
            f"Stage: {context.current_stage}\n"
            f"Attempt: {context.retry_count + 1}\n"
            f"Project: {_safe(context.idea, 150)}\n\n"
            f"Current files:\n{code_summary}\n\n"
        )

        if critique_history:
            user_prompt += f"Previous critique feedback:\n{critique_history}\n\n"
        else:
            user_prompt += "This is the FIRST attempt (no previous critique).\n\n"

        # Include the latest code for evaluation
        code_dump = "\n".join(
            f"### {f}\n```\n{_safe(c, 1000)}\n```"
            for f, c in list(context.code_files.items())[:5]
        )
        user_prompt += f"Code:\n{code_dump}\n\nEvaluate and decide."

        result = await self.call_llm(system_prompt, user_prompt, json_mode=True)
        content = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

        decision = result.get("decision", "escalate") if isinstance(result, dict) else "escalate"
        improvement = result.get("improvement_score", 0) if isinstance(result, dict) else 0
        feedback = result.get("feedback_for_agent", "") if isinstance(result, dict) else ""
        confidence = result.get("confidence", 0) if isinstance(result, dict) else 0

        self.logger.info(
            "self_eval_decision",
            project_id=context.project_id,
            decision=decision,
            improvement_score=improvement,
            confidence=confidence,
            attempt=context.retry_count + 1,
        )

        return AgentOutput(
            agent_name=self.name,
            artifact_type="self_evaluation",
            content=content,
            metadata={
                "decision": decision,
                "improvement_score": improvement,
                "feedback": feedback,
                "confidence": confidence,
            },
        )
