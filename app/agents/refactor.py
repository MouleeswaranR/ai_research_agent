"""Refactor Agent – improves code quality, removes duplication, applies patterns."""

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.tools.ast_analyzer import ASTAnalyzerTool
from app.tools.complexity import CyclomaticComplexityTool
from app.tools.file_ops import ListFilesTool, ReadFileTool, WriteFileTool
from app.tools.linter import RuffFixTool, RuffLintTool


class RefactorAgent(BaseAgent):
    name = "refactor"
    description = "Removes duplication, improves readability, applies design patterns"
    max_tokens = 8192

    def __init__(self) -> None:
        super().__init__()
        self.tools = [
            WriteFileTool(),
            ReadFileTool(),
            ListFilesTool(),
            ASTAnalyzerTool(),
            RuffLintTool(),
            RuffFixTool(),
            CyclomaticComplexityTool(),
        ]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("refactoring", project_id=context.project_id)
        self._build_tool_context(context)

        llm = ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.2,
            max_tokens=self.max_tokens,
        )
        llm_with_tools = llm.bind_tools(self.tools)

        system_msg = SystemMessage(content=(
            "You are a senior refactoring engineer. Improve the codebase.\n"
            "Rules:\n"
            "- Use ast_analyze to identify code smells\n"
            "- Use cyclomatic_complexity to find complex functions\n"
            "- Apply DRY, SOLID, and design patterns\n"
            "- Read files, refactor, write back\n"
            "- Run ruff_lint after changes\n"
            "- Don't change functionality – only improve structure\n"
            "- Keep responses minimal"
        ))

        input_text = (
            f"Files to refactor: {list(context.code_files.keys())}\n\n"
            "Analyze, refactor, and lint all files."
        )
        critique = self._format_critique(context)
        if critique:
            input_text += critique

        messages = [system_msg, HumanMessage(content=input_text)]

        # Tool-calling loop
        tool_map = {t.name: t for t in self.tools}
        for _ in range(12):
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                break

            for tc in response.tool_calls:
                tool = tool_map.get(tc["name"])
                if tool:
                    result = tool.invoke(tc["args"])
                else:
                    result = f"Unknown tool: {tc['name']}"
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        final_output = response.content if response else ""

        self.logger.info("refactoring_complete", project_id=context.project_id)
        return AgentOutput(
            agent_name=self.name,
            artifact_type="refactor",
            content=json.dumps({"output": final_output}),
        )
