"""Linter tool – run Ruff inside sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox
from app.tools.base import SandboxedTool


class LintInput(BaseModel):
    path: str = Field(default=".", description="File or directory to lint (relative to workspace)")


class RuffLintTool(SandboxedTool):
    name: str = "ruff_lint"
    description: str = "Run Ruff linter on code. Returns violations with line numbers and severity."
    args_schema: type[BaseModel] = LintInput

    def _run(self, path: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"ruff check /workspace/{path} --output-format json 2>/dev/null || true",
            timeout=30,
        )
        if result.stdout.strip():
            return result.stdout
        return "✅ No lint issues found"


class RuffFixTool(SandboxedTool):
    name: str = "ruff_fix"
    description: str = "Auto-fix lint issues with Ruff."
    args_schema: type[BaseModel] = LintInput

    def _run(self, path: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"ruff check /workspace/{path} --fix --output-format json 2>/dev/null || true",
            timeout=30,
        )
        return result.stdout or "✅ Auto-fix applied"
