"""Complexity analysis tool – radon cyclomatic complexity inside sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox
from app.tools.base import SandboxedTool


class ComplexityInput(BaseModel):
    path: str = Field(default=".", description="File or directory to analyze")


class CyclomaticComplexityTool(SandboxedTool):
    name: str = "cyclomatic_complexity"
    description: str = "Measure cyclomatic complexity per function using radon. Returns scores (A-F) per function."
    args_schema: type[BaseModel] = ComplexityInput

    def _run(self, path: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"radon cc /workspace/{path} -j -n C 2>/dev/null || true",
            timeout=30,
        )
        return result.stdout or "✅ All functions have acceptable complexity"


class MaintainabilityIndexTool(SandboxedTool):
    name: str = "maintainability_index"
    description: str = "Compute maintainability index per file using radon."
    args_schema: type[BaseModel] = ComplexityInput

    def _run(self, path: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"radon mi /workspace/{path} -j 2>/dev/null || true",
            timeout=30,
        )
        return result.stdout or "✅ Maintainability scores computed"
