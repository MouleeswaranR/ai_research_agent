"""Tests for the pipeline state machine."""

import pytest
from app.orchestrator.state import (
    PipelineStage,
    STAGE_AGENT_MAP,
    next_stage,
    is_review_stage,
    get_retry_stage,
    REVIEW_RETRY_MAP,
)


class TestPipelineState:
    """Test pipeline stage transitions and review gates."""

    def test_all_stages_have_agents(self):
        """Every non-terminal stage maps to an agent."""
        for stage in PipelineStage:
            if stage == PipelineStage.COMPLETED or stage == PipelineStage.IDEA:
                continue
            assert stage.value in STAGE_AGENT_MAP, f"Stage {stage} has no agent mapping"

    def test_next_stage_progression(self):
        """Stages progress in correct order."""
        assert next_stage("prd") == "architecture"
        assert next_stage("architecture") == "security"
        assert next_stage("code_review") == "test_writing"
        assert next_stage("quality_eval") == "completed"

    def test_completed_has_no_next(self):
        assert next_stage("completed") is None

    def test_review_stages_identified(self):
        assert is_review_stage("doc_review") is True
        assert is_review_stage("code_review") is True
        assert is_review_stage("code_generation") is False

    def test_retry_routing(self):
        assert get_retry_stage("code_review") == "code_generation"
        assert get_retry_stage("test_review") == "test_writing"
        assert get_retry_stage("spec_review") == "tech_spec"

    def test_all_review_gates_have_retry_targets(self):
        for gate in REVIEW_RETRY_MAP:
            target = REVIEW_RETRY_MAP[gate]
            assert target in STAGE_AGENT_MAP, f"Retry target {target} has no agent"


class TestReviewGateCount:
    """Verify the expected number of review gates."""

    def test_six_review_gates(self):
        assert len(REVIEW_RETRY_MAP) == 6

    def test_review_gates_all_use_code_reviewer(self):
        for gate in REVIEW_RETRY_MAP:
            assert STAGE_AGENT_MAP[gate] == "code_reviewer"
