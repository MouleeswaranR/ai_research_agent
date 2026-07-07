"""ReviewResult model – per-gate pass/fail verdict from the Code Reviewer."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class ReviewResult(Base):
    __tablename__ = "review_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False
    )
    gate_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "spec_review", "code_review", "test_review", "refactor_review"
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    issues: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    scores: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {security, quality, coverage, complexity, maintainability}
    critique: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    attempt: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    pipeline_run = relationship("PipelineRun", back_populates="review_results")
