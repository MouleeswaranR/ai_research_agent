"""Test Writer Agent – generates tests using tools."""

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq

from app.agents.base import AgentOutput, BaseAgent, PipelineContext
from app.config import settings
from app.tools.code_executor import ExecutePythonTool
from app.tools.file_ops import ListFilesTool, ReadFileTool, WriteFileTool
from app.tools.test_runner import PytestRunnerTool


class TestWriterAgent(BaseAgent):
    name = "test_writer"
    description = "Writes unit, integration, and edge-case tests"
    max_tokens = 8192

    def __init__(self) -> None:
        super().__init__()
        self.tools = [
            WriteFileTool(),
            ReadFileTool(),
            ListFilesTool(),
            ExecutePythonTool(),
            PytestRunnerTool(),
        ]

    async def run(self, context: PipelineContext) -> AgentOutput:
        self.logger.info("writing_tests", project_id=context.project_id)
        self._build_tool_context(context)

        llm = ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.2,
            max_tokens=self.max_tokens,
        )
        llm_with_tools = llm.bind_tools(self.tools)

        system_msg = SystemMessage(content=(
            "You are an expert test engineer. Write comprehensive tests.\n"
            "Rules:\n"
            "- Write unit tests, integration tests, and edge-case tests\n"
            "- Use pytest style with descriptive names\n"
            "- Mock external services\n"
            "- Aim for >=85% coverage\n"
            "- Use tools: write_file for test files, run_tests to execute\n"
            "- Place tests in tests/ directory\n"
            "- After writing, run tests to verify they pass\n"
            "- Keep responses minimal – focus on using tools"
        ))

        # Build context from code files
        code_summary = "\n".join(
            f"### {path}\n```python\n{code[:500]}\n```" for path, code in list(context.code_files.items())[:10]
        )

        input_text = (
            f"Source code files:\n{code_summary}\n\n"
            f"Tech Spec edge cases:\n{context.tech_spec[:1500]}\n\n"
            "Write comprehensive tests. Use write_file to create test files in tests/, then run_tests."
        )
        critique = self._format_critique(context)
        if critique:
            input_text += critique

        messages = [system_msg, HumanMessage(content=input_text)]

        # Tool-calling loop
        tool_map = {t.name: t for t in self.tools}
        for _ in range(15):
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

        # Collect test files
        from app.sandbox.executor import list_sandbox_files, read_from_sandbox
        files = list_sandbox_files(context.project_id, "tests")
        test_files = {}
        for f in files:
            content = read_from_sandbox(context.project_id, f)
            if content:
                test_files[f] = content

        context.test_files = test_files
        final_output = response.content if response else ""

        self.logger.info("tests_written", project_id=context.project_id, test_files=len(test_files))
        return AgentOutput(
            agent_name=self.name,
            artifact_type="test",
            content=json.dumps({"test_files": list(test_files.keys()), "output": final_output}),
            metadata={"test_file_count": len(test_files)},
        )
