from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("agent_zero", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "dispatch-investigation-outbox": {
            "task": "agent_zero.dispatch_outbox",
            "schedule": 2.0,
        }
    },
)

import app.tasks  # noqa: E402,F401
