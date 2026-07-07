"""AST analyzer tool – pattern detection, interface extraction, duplication."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sandbox.executor import exec_in_sandbox, write_to_sandbox
from app.tools.base import SandboxedTool

_AST_SCRIPT = '''\
import ast, sys, json

def analyze(filepath):
    with open(filepath) as f:
        tree = ast.parse(f.read())
    result = {"classes": [], "functions": [], "imports": [], "issues": []}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            result["classes"].append({"name": node.name, "line": node.lineno, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            result["functions"].append({"name": node.name, "line": node.lineno, "args": args})
            if len(node.body) > 50:
                result["issues"].append(f"Function {node.name} at line {node.lineno} is too long ({len(node.body)} statements)")
            if len(args) > 5:
                result["issues"].append(f"Function {node.name} has too many parameters ({len(args)})")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None)
            names = [alias.name for alias in node.names]
            result["imports"].append({"module": module, "names": names})
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    analyze(sys.argv[1])
'''


class ASTInput(BaseModel):
    filepath: str = Field(description="Python file to analyze (relative to workspace)")


class ASTAnalyzerTool(SandboxedTool):
    name: str = "ast_analyze"
    description: str = "Analyze Python file structure: classes, functions, imports, and code smell detection."
    args_schema: type[BaseModel] = ASTInput

    def _run(self, filepath: str) -> str:
        write_to_sandbox(self.project_id, "__ast_analyze__.py", _AST_SCRIPT)
        result = exec_in_sandbox(
            self.project_id,
            f"python /workspace/__ast_analyze__.py /workspace/{filepath}",
            timeout=15,
        )
        return result.stdout or result.stderr
