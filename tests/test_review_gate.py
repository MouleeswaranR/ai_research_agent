"""Tests for review gate logic."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.base import PipelineContext, AgentOutput
from app.orchestrator.review_gate import should_retry, inject_critique


class TestReviewGateLogic:
    """Test review gate retry and critique injection."""

    def test_should_retry_within_limit(self):
        ctx = PipelineContext(project_id="test", idea="test", retry_count=0)
        assert should_retry(ctx) is True

    def test_should_not_retry_at_limit(self):
        ctx = PipelineContext(project_id="test", idea="test", retry_count=3)
        assert should_retry(ctx) is False

    def test_inject_critique_adds_to_context(self):
        ctx = PipelineContext(project_id="test", idea="test", retry_count=0)
        review_output = AgentOutput(
            agent_name="code_reviewer",
            artifact_type="review",
            content=json.dumps({
                "pass": False,
                "summary": "Security vulnerabilities found",
                "issues": [
                    {"severity": "high", "file": "main.py", "line": 10, "message": "SQL injection risk"}
                ],
            }),
        )
        ctx = inject_critique(ctx, review_output)
        assert len(ctx.review_critiques) == 1
        assert "SQL injection" in ctx.review_critiques[0]
        assert ctx.retry_count == 1

    def test_multiple_critiques_accumulated(self):
        ctx = PipelineContext(project_id="test", idea="test", retry_count=0)
        for i in range(3):
            review_output = AgentOutput(
                agent_name="code_reviewer",
                artifact_type="review",
                content=json.dumps({"pass": False, "summary": f"Issue {i}", "issues": []}),
            )
            ctx = inject_critique(ctx, review_output)
        assert len(ctx.review_critiques) == 3
        assert ctx.retry_count == 3
