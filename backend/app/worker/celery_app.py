from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "algo_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        "reset-daily-risk": {
            "task": "app.worker.tasks.reset_daily_risk",
            "schedule": 33300.0,  # 9:15 AM IST = 3:45 AM UTC
        },
    },
)
