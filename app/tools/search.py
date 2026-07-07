"""Search tool – grep-style codebase search inside sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox
from app.tools.base import SandboxedTool


class GrepSearchInput(BaseModel):
    pattern: str = Field(description="Search pattern (regex supported)")
    path: str = Field(default=".", description="Directory to search in")


class FindFilesInput(BaseModel):
    pattern: str = Field(default="*.py", description="Glob pattern for files")
    directory: str = Field(default=".", description="Directory to search")


class GrepSearchTool(SandboxedTool):
    name: str = "grep_search"
    description: str = "Search for a pattern in the codebase using grep. Returns matching lines with file and line numbers."
    args_schema: type[BaseModel] = GrepSearchInput

    def _run(self, pattern: str, path: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"grep -rn '{pattern}' /workspace/{path} --include='*.py' | head -50",
            timeout=15,
        )
        return result.stdout or "No matches found"


class FindFilesTool(SandboxedTool):
    name: str = "find_files"
    description: str = "Find files matching a pattern in the workspace."
    args_schema: type[BaseModel] = FindFilesInput

    def _run(self, pattern: str = "*.py", directory: str = ".") -> str:
        result = exec_in_sandbox(
            self.project_id,
            f"find /workspace/{directory} -name '{pattern}' -type f | head -50",
            timeout=15,
        )
        if result.stdout:
            return "\n".join(
                line.replace("/workspace/", "") for line in result.stdout.strip().split("\n") if line
            )
        return "No files found"
