"""Test runner tool – run pytest + coverage inside sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox
from app.tools.base import SandboxedTool


class TestRunInput(BaseModel):
    test_path: str = Field(default="tests/", description="Test directory or file")
    with_coverage: bool = Field(default=True, description="Include coverage report")


class PytestRunnerTool(SandboxedTool):
    name: str = "run_tests"
    description: str = "Run pytest with optional coverage. Returns pass/fail, coverage %, and uncovered lines."
    args_schema: type[BaseModel] = TestRunInput

    def _run(self, test_path: str = "tests/", with_coverage: bool = True) -> str:
        cmd = f"cd /workspace && python -m pytest {test_path} -v --tb=short"
        if with_coverage:
            cmd += " --cov=. --cov-report=json:/workspace/coverage.json --cov-report=term"
        result = exec_in_sandbox(self.project_id, cmd, timeout=60)

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n{result.stderr}"

        # Append coverage summary if available
        if with_coverage:
            cov_result = exec_in_sandbox(
                self.project_id, "cat /workspace/coverage.json 2>/dev/null || echo '{}'", timeout=5
            )
            if cov_result.stdout.strip() != "{}":
                output += f"\n\nCOVERAGE JSON:\n{cov_result.stdout[:2000]}"

        return output
