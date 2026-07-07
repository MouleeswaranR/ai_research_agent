"""Pipeline state definitions – stages and transitions."""

from __future__ import annotations

from enum import Enum


class PipelineStage(str, Enum):
    """All pipeline stages in order."""

    IDEA = "idea"
    PRD = "prd"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    DOC_REVIEW = "doc_review"          # Review Gate 1
    TECH_SPEC = "tech_spec"
    SPEC_REVIEW = "spec_review"        # Review Gate 2
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"        # Review Gate 3
    TEST_WRITING = "test_writing"
    TEST_REVIEW = "test_review"        # Review Gate 4
    REFACTOR = "refactor"
    REFACTOR_REVIEW = "refactor_review"  # Review Gate 5
    DEPLOYMENT = "deployment"
    DEPLOY_REVIEW = "deploy_review"    # Review Gate 6
    MONITORING = "monitoring"
    QUALITY_EVAL = "quality_eval"
    COMPLETED = "completed"


# Stage → agent name mapping
STAGE_AGENT_MAP: dict[str, str] = {
    PipelineStage.PRD: "product_strategist",
    PipelineStage.ARCHITECTURE: "system_architect",
    PipelineStage.SECURITY: "security_architect",
    PipelineStage.DOC_REVIEW: "code_reviewer",
    PipelineStage.TECH_SPEC: "planner",
    PipelineStage.SPEC_REVIEW: "code_reviewer",
    PipelineStage.CODE_GENERATION: "code_generator",
    PipelineStage.CODE_REVIEW: "code_reviewer",
    PipelineStage.TEST_WRITING: "test_writer",
    PipelineStage.TEST_REVIEW: "code_reviewer",
    PipelineStage.REFACTOR: "refactor",
    PipelineStage.REFACTOR_REVIEW: "code_reviewer",
    PipelineStage.DEPLOYMENT: "deployment",
    PipelineStage.DEPLOY_REVIEW: "code_reviewer",
    PipelineStage.MONITORING: "monitoring",
    PipelineStage.QUALITY_EVAL: "quality_evaluator",
}

# Ordered stage transitions
STAGE_ORDER = list(PipelineStage)

# Review gate → producing stage (for retry routing)
REVIEW_RETRY_MAP: dict[str, str] = {
    PipelineStage.DOC_REVIEW: PipelineStage.ARCHITECTURE,
    PipelineStage.SPEC_REVIEW: PipelineStage.TECH_SPEC,
    PipelineStage.CODE_REVIEW: PipelineStage.CODE_GENERATION,
    PipelineStage.TEST_REVIEW: PipelineStage.TEST_WRITING,
    PipelineStage.REFACTOR_REVIEW: PipelineStage.REFACTOR,
    PipelineStage.DEPLOY_REVIEW: PipelineStage.DEPLOYMENT,
}


def next_stage(current: str) -> str | None:
    """Return the next stage, or None if completed."""
    try:
        idx = STAGE_ORDER.index(PipelineStage(current))
        if idx + 1 < len(STAGE_ORDER):
            return STAGE_ORDER[idx + 1].value
    except (ValueError, IndexError):
        pass
    return None


def is_review_stage(stage: str) -> bool:
    """Check if a stage is a review gate."""
    return stage in REVIEW_RETRY_MAP


def get_retry_stage(review_stage: str) -> str | None:
    """Get the producing stage to retry on review failure."""
    return REVIEW_RETRY_MAP.get(review_stage)
