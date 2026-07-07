"""Celery application – uses Redis as broker and result backend."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "auto_dev_company",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task behavior
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Result expiry
    result_expires=3600,  # 1 hour
    # Task routes
    task_routes={
        "app.orchestrator.tasks.run_agent_task": {"queue": "agents"},
        "app.orchestrator.tasks.run_pipeline": {"queue": "pipeline"},
        "app.orchestrator.tasks.run_review_gate": {"queue": "review"},
    },
)

# Auto-discover tasks in app.orchestrator.tasks
celery_app.autodiscover_tasks(["app.orchestrator"])
