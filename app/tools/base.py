"""Base tool interface for LangChain-compatible agent tools."""

from langchain_core.tools import BaseTool as LangChainBaseTool
from pydantic import ConfigDict


class SandboxedTool(LangChainBaseTool):
    """Base for tools that execute inside the Docker sandbox.

    Subclasses must set `project_id` before invocation via the agent context.
    """

    project_id: str = ""
    model_config = ConfigDict(arbitrary_types_allowed=True)

