"""Sandbox executor – runs commands safely inside Docker containers."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.logging import get_logger
from app.sandbox.manager import create_sandbox, get_sandbox

logger = get_logger("sandbox.executor")


@dataclass
class ExecResult:
    """Result of a sandbox command execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def exec_in_sandbox(
    project_id: str,
    command: str,
    timeout: int | None = None,
    language: str = "python",
) -> ExecResult:
    """Execute a command inside the project's sandbox container.

    Creates the sandbox if it doesn't exist.
    """
    timeout = timeout or settings.sandbox_timeout
    container = get_sandbox(project_id) or create_sandbox(project_id, language)

    logger.info(
        "sandbox_exec",
        project_id=project_id,
        command=command[:200],
        timeout=timeout,
    )

    try:
        exit_code, output = container.exec_run(
            cmd=["sh", "-c", command],
            workdir="/workspace",
            demux=True,
            environment={"PYTHONDONTWRITEBYTECODE": "1"},
        )

        stdout = (output[0] or b"").decode("utf-8", errors="replace")
        stderr = (output[1] or b"").decode("utf-8", errors="replace")

        logger.info(
            "sandbox_exec_result",
            project_id=project_id,
            exit_code=exit_code,
            stdout_len=len(stdout),
            stderr_len=len(stderr),
        )

        return ExecResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    except Exception as e:
        logger.error("sandbox_exec_error", project_id=project_id, error=str(e))
        return ExecResult(exit_code=1, stdout="", stderr=str(e), timed_out=False)


def write_to_sandbox(project_id: str, filepath: str, content: str, language: str = "python") -> bool:
    """Write a file into the sandbox workspace."""
    # Use echo with heredoc to write files
    # Escape content for shell
    escaped = content.replace("\\", "\\\\").replace("'", "'\\''")
    # Ensure parent directory exists
    parent_dir = "/".join(filepath.rsplit("/", 1)[:-1]) if "/" in filepath else ""
    cmd = ""
    if parent_dir:
        cmd = f"mkdir -p /workspace/{parent_dir} && "
    cmd += f"cat > /workspace/{filepath} << 'SANDBOX_EOF'\n{content}\nSANDBOX_EOF"

    result = exec_in_sandbox(project_id, cmd, timeout=10, language=language)
    return result.exit_code == 0


def read_from_sandbox(project_id: str, filepath: str, language: str = "python") -> str | None:
    """Read a file from the sandbox workspace."""
    result = exec_in_sandbox(project_id, f"cat /workspace/{filepath}", timeout=10, language=language)
    if result.exit_code == 0:
        return result.stdout
    return None


def list_sandbox_files(project_id: str, directory: str = ".", language: str = "python") -> list[str]:
    """List files in the sandbox workspace."""
    result = exec_in_sandbox(
        project_id, f"find /workspace/{directory} -type f -name '*.py' | head -100",
        timeout=10, language=language,
    )
    if result.exit_code == 0:
        return [line.replace("/workspace/", "") for line in result.stdout.strip().split("\n") if line]
    return []
