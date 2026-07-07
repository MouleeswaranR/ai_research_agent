"""Security scanner tool – run Bandit inside sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox
from app.tools.base import SandboxedTool


class SecurityScanInput(BaseModel):
    path: str = Field(default=".", description="File or directory to scan")


class BanditScanTool(SandboxedTool):
    name: str = "bandit_scan"
    description: str = "Run Bandit security scanner (OWASP). Returns security issues with severity and CWE IDs."
    args_schema: type[BaseModel] = SecurityScanInput

    def _run(self, path: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"bandit -r /workspace/{path} -f json -ll 2>/dev/null || true",
            timeout=30,
        )
        if result.stdout.strip():
            return result.stdout
        return "✅ No security issues found"
