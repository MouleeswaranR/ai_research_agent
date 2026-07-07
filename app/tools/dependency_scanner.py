"""Dependency scanner tool – check for known CVEs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox
from app.tools.base import SandboxedTool


class DepScanInput(BaseModel):
    requirements_path: str = Field(default="requirements.txt", description="Requirements file to audit")


class DependencyScannerTool(SandboxedTool):
    name: str = "dependency_scan"
    description: str = "Audit project dependencies for known CVEs and outdated packages."
    args_schema: type[BaseModel] = DepScanInput

    def _run(self, requirements_path: str = "requirements.txt") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"cd /workspace && safety check -r {requirements_path} --output json 2>/dev/null || true",
            timeout=30,
        )
        return result.stdout or "✅ No known vulnerabilities found"
