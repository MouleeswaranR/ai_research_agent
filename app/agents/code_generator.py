"""Code Generator Agent – implements backend logic with tools."""

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.tools.code_executor import ExecutePythonTool
from app.tools.file_ops import ListFilesTool, ReadFileTool, WriteFileTool
from app.tools.linter import RuffLintTool
from app.tools.search import GrepSearchTool


class CodeGeneratorAgent(BaseAgent):
    name = "code_generator"
    description = "Implements backend logic, API endpoints, modular code with error handling"
    max_tokens = 16384

    def __init__(self) -> None:
        super().__init__()
        self.tools = [
            WriteFileTool(),
            ReadFileTool(),
            ListFilesTool(),
            ExecutePythonTool(),
            RuffLintTool(),
            GrepSearchTool(),
        ]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("generating_code", project_id=context.project_id)
        self._build_tool_context(context)

        llm = ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.2,
            max_tokens=self.max_tokens,
        )
        llm_with_tools = llm.bind_tools(self.tools)

        system_msg = SystemMessage(content=(
            "You are an expert Python backend developer. Implement the code based on the tech spec.\n"
            "Rules:\n"
            "- Write modular, production-ready code\n"
            "- Add proper error handling and logging\n"
            "- Follow PEP 8 and type hints\n"
            "- Use the tools to write files, run code, and lint\n"
            "- Create a proper project structure\n"
            "- After writing each file, lint it with ruff_lint\n"
            "- Keep responses minimal – focus on using tools"
        ))

        input_text = (
            f"Tech Spec:\n{context.tech_spec[:3000]}\n\n"
            f"Architecture:\n{context.architecture[:2000]}\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Implement ALL modules fully. NEVER use placeholders (e.g. 'TODO', 'pass', '...').\n"
            "2. Ensure completely working code.\n"
            "3. Use a proper multi-file directory structure. DO NOT combine everything into one file.\n"
            "Write each file using write_file, then lint with ruff_lint."
        )
        critique = self._format_critique(context)
        if critique:
            input_text += critique

        messages = [system_msg, HumanMessage(content=input_text)]

        # Tool-calling loop
        tool_map = {t.name: t for t in self.tools}
        for _ in range(15):  # max iterations
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

        # Collect written files from sandbox
        from app.sandbox.executor import list_sandbox_files, read_from_sandbox
        files = list_sandbox_files(context.project_id)
        code_files = {}
        for f in files:
            if not f.startswith("__"):
                content = read_from_sandbox(context.project_id, f)
                if content:
                    code_files[f] = content

        context.code_files = code_files
        final_output = response.content if response else ""

        self.logger.info("code_generated", project_id=context.project_id, files=len(code_files))
        return AgentOutput(
            agent_name=self.name,
            artifact_type="code",
            content=json.dumps({"files": list(code_files.keys()), "agent_output": final_output}),
            metadata={"file_count": len(code_files)},
        )
