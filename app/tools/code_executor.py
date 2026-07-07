"""Code executor tool – run Python code in sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox, write_to_sandbox
from app.tools.base import SandboxedTool


class ExecuteCodeInput(BaseModel):
    code: str = Field(description="Python code to execute")
    filename: str = Field(default="__run__.py", description="Filename to save as")


class ExecutePythonTool(SandboxedTool):
    name: str = "execute_python"
    description: str = "Execute Python code in a sandboxed environment. Returns stdout, stderr, and exit code."
    args_schema: type[BaseModel] = ExecuteCodeInput

    def _run(self, code: str, filename: str = "__run__.py") -> str:
        write_to_sandbox(self.project_id, filename, code)
        result = exec_in_sandbox(self.project_id, f"python /workspace/{filename}", timeout=30)
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        output += f"EXIT CODE: {result.exit_code}"
        if result.timed_out:
            output += "\n⚠️ TIMED OUT"
        return output
