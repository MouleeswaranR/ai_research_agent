"""Sandbox manager – creates/destroys ephemeral Docker containers."""

from __future__ import annotations

import docker
from docker.models.containers import Container

from app.config import settings
from app.logging import get_logger

logger = get_logger("sandbox.manager")

# Cache of active containers: project_id → container
_active_sandboxes: dict[str, Container] = {}


def _get_docker_client() -> docker.DockerClient:
    """Return a Docker client connected to the local daemon."""
    return docker.from_env()


def create_sandbox(project_id: str, language: str = "python") -> Container:
    """Create an ephemeral sandbox container for a project.

    - Mounts a per-project workspace volume at /workspace
    - Sets resource limits (CPU, memory, no network)
    - Pre-installs code quality tools
    """
    if project_id in _active_sandboxes:
        existing = _active_sandboxes[project_id]
        existing.reload()
        if existing.status == "running":
            logger.info("reusing_sandbox", project_id=project_id)
            return existing
        else:
            # Container died – clean up and recreate
            _cleanup(project_id)

    client = _get_docker_client()
    image = f"autodev-sandbox-{language}"

    # Build image if it doesn't exist
    _ensure_image(client, image, language)

    container = client.containers.run(
        image=image,
        name=f"sandbox-{project_id[:8]}",
        command="sleep infinity",  # Keep alive for multiple exec calls
        detach=True,
        mem_limit=settings.sandbox_memory_limit,
        nano_cpus=int(settings.sandbox_cpu_limit * 1e9),
        network_disabled=settings.sandbox_network_disabled,
        volumes={
            f"sandbox-workspace-{project_id[:8]}": {
                "bind": "/workspace",
                "mode": "rw",
            }
        },
        working_dir="/workspace",
        auto_remove=False,
    )

    _active_sandboxes[project_id] = container
    logger.info(
        "sandbox_created",
        project_id=project_id,
        container_id=container.short_id,
        language=language,
    )
    return container


def get_sandbox(project_id: str) -> Container | None:
    """Get existing sandbox for a project, or None."""
    container = _active_sandboxes.get(project_id)
    if container:
        container.reload()
        if container.status == "running":
            return container
        _cleanup(project_id)
    return None


def destroy_sandbox(project_id: str) -> None:
    """Kill container and remove workspace volume."""
    _cleanup(project_id)
    # Also remove the volume
    try:
        client = _get_docker_client()
        vol_name = f"sandbox-workspace-{project_id[:8]}"
        vol = client.volumes.get(vol_name)
        vol.remove(force=True)
        logger.info("sandbox_volume_removed", project_id=project_id)
    except docker.errors.NotFound:
        pass


def _cleanup(project_id: str) -> None:
    """Stop and remove a container."""
    container = _active_sandboxes.pop(project_id, None)
    if container:
        try:
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info("sandbox_destroyed", project_id=project_id)
        except Exception as e:
            logger.warning("sandbox_cleanup_error", project_id=project_id, error=str(e))


def _ensure_image(client: docker.DockerClient, image_name: str, language: str) -> None:
    """Build sandbox image if it doesn't exist."""
    try:
        client.images.get(image_name)
    except docker.errors.ImageNotFound:
        logger.info("building_sandbox_image", image=image_name)
        dockerfile_content = _get_dockerfile(language)
        import io
        import tarfile

        # Build from string
        f = io.BytesIO()
        tar = tarfile.open(fileobj=f, mode="w")
        dockerfile_bytes = dockerfile_content.encode("utf-8")
        info = tarfile.TarInfo(name="Dockerfile")
        info.size = len(dockerfile_bytes)
        tar.addfile(info, io.BytesIO(dockerfile_bytes))
        tar.close()
        f.seek(0)

        client.images.build(fileobj=f, custom_context=True, tag=image_name, rm=True)
        logger.info("sandbox_image_built", image=image_name)


def _get_dockerfile(language: str) -> str:
    """Return Dockerfile content for the given language."""
    if language == "python":
        return """\
FROM python:3.12-slim
RUN pip install --no-cache-dir ruff bandit pytest pytest-cov radon safety
WORKDIR /workspace
"""
    elif language == "node":
        return """\
FROM node:20-slim
RUN apt-get update && apt-get install -y python3 python3-pip --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir --break-system-packages ruff bandit pytest pytest-cov radon safety
RUN npm install -g eslint
WORKDIR /workspace
"""
    else:
        return """\
FROM python:3.12-slim
RUN pip install --no-cache-dir ruff bandit pytest pytest-cov radon safety
WORKDIR /workspace
"""
