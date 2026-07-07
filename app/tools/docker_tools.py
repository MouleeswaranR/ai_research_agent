"""Docker tools – generate and validate Dockerfiles."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import read_from_sandbox, write_to_sandbox
from app.tools.base import SandboxedTool


class DockerGenInput(BaseModel):
    app_type: str = Field(description="Application type: python, node, go")
    entry_point: str = Field(default="main.py", description="Application entry point")
    port: int = Field(default=8000, description="Port to expose")


class DockerfileGeneratorTool(SandboxedTool):
    name: str = "generate_dockerfile"
    description: str = "Generate a production-ready Dockerfile for the project."
    args_schema: type[BaseModel] = DockerGenInput

    def _run(self, app_type: str, entry_point: str = "main.py", port: int = 8000) -> str:
        templates = {
            "python": f"""\
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
EXPOSE {port}
CMD ["python", "{entry_point}"]
""",
            "node": f"""\
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci --only=production

FROM node:20-slim
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .
EXPOSE {port}
CMD ["node", "{entry_point}"]
""",
        }
        content = templates.get(app_type, templates["python"])
        write_to_sandbox(self.project_id, "Dockerfile", content)
        return f"✅ Dockerfile generated:\n{content}"


class DockerValidateInput(BaseModel):
    pass


class DockerfileValidatorTool(SandboxedTool):
    name: str = "validate_dockerfile"
    description: str = "Validate the generated Dockerfile for common issues."
    args_schema: type[BaseModel] = DockerValidateInput

    def _run(self) -> str:
        content = read_from_sandbox(self.project_id, "Dockerfile")
        if not content:
            return "❌ No Dockerfile found"
        issues = []
        if "latest" in content:
            issues.append("⚠️ Avoid using 'latest' tag – pin specific versions")
        if "COPY . ." in content and "dockerignore" not in content.lower():
            issues.append("⚠️ Consider adding .dockerignore to exclude unnecessary files")
        if "HEALTHCHECK" not in content:
            issues.append("💡 Consider adding a HEALTHCHECK instruction")
        if not issues:
            return "✅ Dockerfile looks good"
        return "\n".join(issues)
