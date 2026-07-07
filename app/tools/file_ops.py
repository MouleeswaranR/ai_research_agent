"""File operations tool – read/write/list files inside the sandbox."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import (
    list_sandbox_files,
    read_from_sandbox,
    write_to_sandbox,
)
from app.tools.base import SandboxedTool


class WriteFileInput(BaseModel):
    filepath: str = Field(description="Path relative to workspace root")
    content: str = Field(description="File content to write")


class ReadFileInput(BaseModel):
    filepath: str = Field(description="Path relative to workspace root")


class ListFilesInput(BaseModel):
    directory: str = Field(default=".", description="Directory to list")


class WriteFileTool(SandboxedTool):
    name: str = "write_file"
    description: str = "Write content to a file in the project workspace"
    args_schema: type[BaseModel] = WriteFileInput

    def _run(self, filepath: str, content: str) -> str:
        success = write_to_sandbox(self.project_id, filepath, content)
        return f"✅ Written to {filepath}" if success else f"❌ Failed to write {filepath}"


class ReadFileTool(SandboxedTool):
    name: str = "read_file"
    description: str = "Read a file from the project workspace"
    args_schema: type[BaseModel] = ReadFileInput

    def _run(self, filepath: str) -> str:
        content = read_from_sandbox(self.project_id, filepath)
        if content is not None:
            return content
        return f"❌ File not found: {filepath}"


class ListFilesTool(SandboxedTool):
    name: str = "list_files"
    description: str = "List Python files in a directory of the project workspace"
    args_schema: type[BaseModel] = ListFilesInput

    def _run(self, directory: str = ".") -> str:
        files = list_sandbox_files(self.project_id, directory)
        if files:
            return "\n".join(files)
        return "No files found"
