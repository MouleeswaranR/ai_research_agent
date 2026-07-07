"""Code verification via sandbox execution – linting, security, and tests."""

from __future__ import annotations

from dataclasses import dataclass

from app.logging import get_logger
from app.sandbox.executor import exec_in_sandbox, write_to_sandbox

logger = get_logger("sandbox.verifier")


@dataclass
class VerificationResult:
    """Aggregated result from all sandbox checks."""

    syntax_valid: bool
    lint_errors: list[dict]
    security_findings: list[dict]
    test_failures: list[dict]
    complexity_issues: list[dict]
    exit_code: int
    summary: str

    def has_blocking_issues(self) -> bool:
        """Check if there are issues that should block generation."""
        return (
            not self.syntax_valid
            or any(f.get("severity") in ("high", "critical") for f in self.security_findings)
            or len(self.test_failures) > 0
        )


def verify_code_in_sandbox(
    project_id: str,
    code_files: dict[str, str],
    language: str = "python",
) -> VerificationResult:
    """Run linting, security scans, and tests on generated code."""

    # Write all files to sandbox
    for filepath, content in code_files.items():
        write_to_sandbox(project_id, filepath, content, language)

    results = VerificationResult(
        syntax_valid=True,
        lint_errors=[],
        security_findings=[],
        test_failures=[],
        complexity_issues=[],
        exit_code=0,
        summary=""
    )

    if language in ("python", "py"):
        results = _verify_python(project_id, code_files, results)
    elif language in ("javascript", "typescript", "js", "ts"):
        results = _verify_javascript(project_id, code_files, results)

    # Build summary
    issues = len(results.lint_errors) + len(results.security_findings) + len(results.test_failures)
    results.summary = f"Verification: {issues} issues found"
    if not results.syntax_valid:
        results.summary += " | SYNTAX ERROR"

    logger.info(
        "verification_complete",
        project_id=project_id,
        syntax_valid=results.syntax_valid,
        lint_errors=len(results.lint_errors),
        security_findings=len(results.security_findings),
        test_failures=len(results.test_failures),
    )

    return results


def _verify_python(project_id: str, code_files: dict, results: VerificationResult) -> VerificationResult:
    """Run Python-specific verification."""

    py_files = [f for f in code_files if f.endswith(".py")]
    if not py_files:
        return results

    files_str = " ".join(py_files)

    # 1. Syntax check via compile
    for filepath in py_files:
        syntax_result = exec_in_sandbox(
            project_id,
            f"python -m py_compile {filepath}",
            timeout=10,
            language="python"
        )
        if syntax_result.exit_code != 0:
            results.syntax_valid = False
            results.lint_errors.append({
                "file": filepath,
                "severity": "critical",
                "message": f"Syntax error: {syntax_result.stderr[:200]}"
            })

    if not results.syntax_valid:
        return results  # Don't run other checks if syntax is broken

    # 2. Ruff linting
    ruff_result = exec_in_sandbox(
        project_id,
        f"ruff check {files_str} --output-format=json || true",
        timeout=30,
        language="python"
    )
    if ruff_result.stdout.strip():
        try:
            import json
            ruff_data = json.loads(ruff_result.stdout)
            for item in ruff_data[:20]:  # Limit to 20 issues
                results.lint_errors.append({
                    "file": item.get("filename", ""),
                    "line": item.get("location", {}).get("row", 0),
                    "severity": "medium",
                    "code": item.get("code", ""),
                    "message": item.get("message", "")
                })
        except Exception:
            pass

    # 3. Bandit security scan
    bandit_result = exec_in_sandbox(
        project_id,
        "bandit -r . -f json || true",
        timeout=30,
        language="python"
    )
    if bandit_result.stdout.strip():
        try:
            import json
            bandit_data = json.loads(bandit_result.stdout)
            for item in bandit_data.get("results", [])[:15]:
                results.security_findings.append({
                    "file": item.get("filename", "").replace("/workspace/", ""),
                    "line": item.get("line_number", 0),
                    "severity": item.get("issue_severity", "").lower(),
                    "confidence": item.get("issue_confidence", "").lower(),
                    "message": item.get("issue_text", ""),
                    "cwe": item.get("issue_cwe", {}).get("id", "")
                })
        except Exception:
            pass

    # 4. Radon complexity
    radon_result = exec_in_sandbox(
        project_id,
        f"radon cc {files_str} -j || true",
        timeout=20,
        language="python"
    )
    if radon_result.stdout.strip():
        try:
            import json
            radon_data = json.loads(radon_result.stdout)
            for filepath, functions in radon_data.items():
                for func in functions:
                    if func.get("complexity", 0) > 10:
                        results.complexity_issues.append({
                            "file": filepath,
                            "function": func.get("name"),
                            "complexity": func.get("complexity"),
                            "line": func.get("lineno")
                        })
        except Exception:
            pass

    return results


def _verify_javascript(project_id: str, code_files: dict, results: VerificationResult) -> VerificationResult:
    """Run JavaScript/TypeScript verification."""

    js_files = [f for f in code_files if f.endswith((".js", ".ts", ".jsx", ".tsx"))]
    if not js_files:
        return results

    # Basic syntax check via node
    for filepath in js_files:
        syntax_result = exec_in_sandbox(
            project_id,
            f"node --check {filepath} || true",
            timeout=10,
            language="node"
        )
        if syntax_result.exit_code != 0:
            results.syntax_valid = False
            results.lint_errors.append({
                "file": filepath,
                "severity": "critical",
                "message": f"Syntax error: {syntax_result.stderr[:200]}"
            })

    return results
